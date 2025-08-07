import asyncio
import time
import requests
import json
import RPi.GPIO as GPIO
import serial
from bleak import BleakScanner
import psycopg2

# --- DATABASE CONFIGURATION ---
DB_HOST = "localhost"
DB_NAME = "laptop_security_db"
DB_USER = "justine"

DB_PASSWORD = "justine123"

# --- FLASK CONFIGURATION ---
FLASK_DATA_API_URL = "http://localhost:5000/api/sensor_data"
FLASK_STATUS_API_URL = "http://localhost:5000/api/laptop_status"
# NEW: API endpoint to create a log entry
FLASK_LOG_API_URL = "http://localhost:5000/api/log_event"

# --- ULTRASONIC SENSOR MAPPING ---
IBEACON_TO_LAPTOP_MAP = {}
ULTRASONIC_SENSOR_TO_LAPTOP_MAP = {}

# --- ALARM THRESHOLD ---
MIN_DISTANCE_CM = 5.0

# Arduino Serial Port Configuration
# --- BUZZER CONFIGURATION ---
BUZZER_PIN = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

alarm_task = None
# Stores the current 'stolen' status for each laptop to detect changes
stolen_laptops_status = {}

def fetch_config_from_db():
    """
    Connects to the PostgreSQL database and fetches the laptop configuration.
    """
    global IBEACON_TO_LAPTOP_MAP, ULTRASONIC_SENSOR_TO_LAPTOP_MAP
    
    ibeacon_map = {}
    ultrasonic_map = {}

    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD)
        cur = conn.cursor()

        cur.execute("SELECT ibeacon_mac_address, serial_number, ultrasonic_sensor_index FROM laptop;")
        rows = cur.fetchall()

        for row in rows:
            ibeacon_mac, serial_number, sensor_index = row
            if ibeacon_mac and serial_number and sensor_index is not None:
                ibeacon_map[ibeacon_mac] = serial_number
                ultrasonic_map[serial_number] = sensor_index

        cur.close()
        conn.close()

        print("Configuration successfully loaded from the database.")
        print(f"iBeacon Map: {ibeacon_map}")
        print(f"Ultrasonic Sensor Map: {ultrasonic_map}")
        
        return ibeacon_map, ultrasonic_map

    except (Exception, psycopg2.Error) as error:
        print(f"Error while connecting to PostgreSQL or fetching data: {error}")
        return {}, {}

async def beeping_alarm():
    try:
        while True:
            for _ in range(3):
                GPIO.output(BUZZER_PIN, GPIO.HIGH)
                await asyncio.sleep(0.1)
                GPIO.output(BUZZER_PIN, GPIO.LOW)
                await asyncio.sleep(0.1)
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        GPIO.output(BUZZER_PIN, GPIO.LOW)
        print("Beeping alarm stopped.")

def log_event_in_db(laptop_serial, event_type):
    """
    Sends a POST request to the Flask API to create a new log entry.
    """
    url = FLASK_LOG_API_URL
    payload = {"serial_number": laptop_serial, "event_type": event_type}
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        print(f"Logged event '{event_type}' for laptop {laptop_serial}.")
    except requests.exceptions.RequestException as e:
        print(f"Error logging event for {laptop_serial}: {e}")

def update_stolen_status(laptop_serial, is_stolen):
    global stolen_laptops_status
    
    # Check if the status has actually changed
    if stolen_laptops_status.get(laptop_serial) != is_stolen:
        url = f"{FLASK_STATUS_API_URL}/{laptop_serial}"
        payload = {"is_stolen": is_stolen}
        try:
            response = requests.post(url, json=payload, timeout=5)
            response.raise_for_status()
            stolen_laptops_status[laptop_serial] = is_stolen
            print(f"Laptop {laptop_serial} status updated to is_stolen={is_stolen} in the database.")
            
            # Call the log function based on the status change
            event_type = 'stolen' if is_stolen else 'returned'
            log_event_in_db(laptop_serial, event_type)
            
        except requests.exceptions.RequestException as e:
            print(f"Error updating laptop status for {laptop_serial}: {e}")

def get_ultrasonic_distances(ser):
    default_distances = [0.0, 0.0, 0.0, 0.0] 
    
    try:
        ser.flushInput()
        line = ser.readline().decode('utf-8').strip()
        
        if line:
            try:
                distances = [float(d) for d in line.split(',')]
                if len(distances) == 4:
                    print(f"Read distances from Arduino: {distances} cm")
                    return distances
            except ValueError:
                print(f"Error parsing line from Arduino: '{line}'")
    except Exception as e:
        print(f"Error reading from Arduino: {e}")
        
    return default_distances

# --- SCANNING AND DATA SENDING LOGIC ---
async def scan_and_send_data():
    global alarm_task, IBEACON_TO_LAPTOP_MAP, ULTRASONIC_SENSOR_TO_LAPTOP_MAP, stolen_laptops_status
    print("Starting iBeacon scanner...")

    found_devices = {}

    def detection_callback(device, advertisement_data):
        if device.address in IBEACON_TO_LAPTOP_MAP:
            rssi = advertisement_data.rssi
            found_devices[device.address] = {
                "rssi": rssi
            }
            print(f"Found target iBeacon ({device.address}) with RSSI: {rssi}")

    scanner = BleakScanner(detection_callback)
    await scanner.start()

    ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1)
    ser.flushInput()

    try:
        while True:
            await asyncio.sleep(2)
            ultrasonic_distances = get_ultrasonic_distances(ser)

            found_mac_addresses = found_devices.keys()
            all_target_macs = IBEACON_TO_LAPTOP_MAP.keys()

            # The logic for checking missing beacons is fine, but let's make sure it updates the status for each one.
            missing_beacons = [mac for mac in all_target_macs if mac not in found_mac_addresses]

            if missing_beacons:
                if not alarm_task:
                    alarm_task = asyncio.create_task(beeping_alarm())
                    print(f"ALARM ACTIVATED! The following beacons are missing: {', '.join(missing_beacons)}")
                for mac in missing_beacons:
                    laptop_serial = IBEACON_TO_LAPTOP_MAP.get(mac)
                    if laptop_serial:
                        update_stolen_status(laptop_serial, True)
            else:
                if alarm_task:
                    # Check if all currently stolen laptops are returned
                    all_returned = True
                    for mac in all_target_macs:
                        laptop_serial = IBEACON_TO_LAPTOP_MAP.get(mac)
                        if stolen_laptops_status.get(laptop_serial):
                            all_returned = False
                            break
                    if all_returned:
                        alarm_task.cancel()
                        alarm_task = None
                        print("All beacons found and laptops are close. Alarm deactivated.")

            for mac_address, beacon_data in found_devices.items():
                laptop_serial = IBEACON_TO_LAPTOP_MAP.get(mac_address)
                
                if laptop_serial:
                    sensor_index = ULTRASONIC_SENSOR_TO_LAPTOP_MAP.get(laptop_serial)
                    
                    is_moved = False
                    if sensor_index is not None:
                        distance = ultrasonic_distances[sensor_index]
                        print(f"Distance for {laptop_serial} (Sensor {sensor_index}): {distance} cm")
                        if distance > MIN_DISTANCE_CM:
                            print(f"Laptop {laptop_serial} moved! Distance is {distance} cm")
                            is_moved = True

                    if is_moved:
                        if not alarm_task:
                            alarm_task = asyncio.create_task(beeping_alarm())
                        update_stolen_status(laptop_serial, True)
                        
                    else:
                        update_stolen_status(laptop_serial, False)

                    # Send normal sensor data regardless of alarm status
                    payload = {
                        "serial_number": laptop_serial,
                        "ibeacon_rssi": beacon_data['rssi'],
                        "ultrasonic_distances": ultrasonic_distances
                    }
                    try:
                        response = requests.post(FLASK_DATA_API_URL, json=payload, timeout=5)
                        response.raise_for_status()
                        print(f"Sent data for {laptop_serial} successfully.")
                    except requests.exceptions.RequestException as e:
                        print(f"Error sending data for {laptop_serial}: {e}")

            found_devices.clear()

    except asyncio.CancelledError:
        print("Scanner stopped.")
    finally:
        if alarm_task:
            alarm_task.cancel()
            try:
                await alarm_task
            except asyncio.CancelledError:
                pass
        await scanner.stop()
        ser.close()
        GPIO.cleanup()

if __name__ == "__main__":
    IBEACON_TO_LAPTOP_MAP, ULTRASONIC_SENSOR_TO_LAPTOP_MAP = fetch_config_from_db()
    stolen_laptops_status = {serial: False for serial in IBEACON_TO_LAPTOP_MAP.values()}

    try:
        if IBEACON_TO_LAPTOP_MAP and ULTRASONIC_SENSOR_TO_LAPTOP_MAP:
            asyncio.run(scan_and_send_data())
        else:
            print("No laptops found in the database. Exiting.")
    except KeyboardInterrupt:
        print("Script terminated by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
        GPIO.cleanup()