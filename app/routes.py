from flask import render_template, flash, redirect, url_for, request, jsonify, current_app
from flask_login import current_user, login_user, logout_user, login_required
from app import app, db
from app.forms import LoginForm, RegistrationForm, LaptopForm
from app.models import User, Laptop, SensorReading, Log
from app.ibeacon_scanner import scan_for_ibeacons
from urllib.parse import urlparse
from datetime import datetime, timedelta
import asyncio
import subprocess
import os
import sys
import pytz

# Global variable to hold the script's process object
sensor_script_process = None

@app.route('/')
@app.route('/index')
@login_required
def index():
    laptops = current_user.laptops.all()
    is_script_running = sensor_script_process is not None and sensor_script_process.poll() is None
    return render_template('index.html', title='Dashboard', laptops=laptops, db=db, SensorReading=SensorReading, is_script_running=is_script_running)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
            return redirect(url_for('login'))

        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)

    return render_template('login.html', title='Sign In', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!')
        return redirect(url_for('login'))

    return render_template('register.html', title='Register', form=form)

# app/routes.py

# app/routes.py

@app.route('/add_laptop', methods=['GET', 'POST'])
@login_required
def add_laptop():
    form = LaptopForm()
    
    # Logic to populate the ultrasonic sensor choices for the form
    used_sensors = db.session.query(Laptop.ultrasonic_sensor_index).filter(
        Laptop.ultrasonic_sensor_index.isnot(None)
    ).all()
    used_sensor_indices = {s[0] for s in used_sensors}
    
    available_indices = [i for i in range(4) if i not in used_sensor_indices]
    form.ultrasonic_sensor_index.choices = [(i, f'Sensor {i}') for i in available_indices]

    if form.validate_on_submit():
        # CORRECTED: Retrieve data using the exact names from the HTML
        uuid = request.form.get('ibeacon_uuid')
        major = request.form.get('ibeacon_major')
        minor = request.form.get('ibeacon_minor')
        rssi = request.form.get('ibeacon_rssi')
        mac_address = request.form.get('ibeacon_mac_address')
        
        ultrasonic_sensor_index = form.ultrasonic_sensor_index.data
        
        if uuid and major and minor and mac_address and ultrasonic_sensor_index is not None:
            laptop = Laptop(
                name=form.name.data,
                serial_number=form.serial_number.data,
                owner=current_user,
                ibeacon_uuid=uuid,
                ibeacon_major=int(major),
                ibeacon_minor=int(minor),
                ibeacon_mac_address=mac_address,
                ultrasonic_sensor_index=ultrasonic_sensor_index 
            )
            db.session.add(laptop)
            db.session.commit()

            if rssi:
                initial_reading = SensorReading(
                    ibeacon_uuid=uuid,
                    ibeacon_major=int(major),
                    ibeacon_minor=int(minor),
                    ibeacon_rssi=int(rssi),
                    ibeacon_mac_address=mac_address,
                    ultrasonic_distance_1_cm=0.0,
                    ultrasonic_distance_2_cm=0.0,
                    ultrasonic_distance_3_cm=0.0,
                    ultrasonic_distance_4_cm=0.0,
                    laptop_id=laptop.id
                )
                db.session.add(initial_reading)
                db.session.commit()

            flash(f"Laptop '{laptop.name}' has been added!", 'success')
            return redirect(url_for('index'))
        else:
            flash('Please select an iBeacon and an ultrasonic sensor.', 'danger')
            return render_template('add_laptop.html', title='Add a New Laptop', form=form)

    return render_template('add_laptop.html', title='Add a New Laptop', form=form)

@app.route('/scan_ibeacons', methods=['POST'])
@login_required
def scan_ibeacons():
    try:
        used = db.session.query(Laptop.ibeacon_uuid, Laptop.ibeacon_major, Laptop.ibeacon_minor).all()
        used_set = set(used)
        beacons_found = asyncio.run(scan_for_ibeacons(scan_duration=10))

        available_beacons = [
            b for b in beacons_found
            if (b['uuid'], b['major'], b['minor']) not in used_set
        ]

        if available_beacons:
            print(f"Found {len(beacons_found)} beacons, {len(available_beacons)} are available.")
            return jsonify({'success': True, 'beacons': available_beacons})
        else:
            return jsonify({'success': False, 'message': 'No new iBeacons found.'})
    except Exception as e:
        current_app.logger.error(f"Error scanning for iBeacons: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/delete_laptop/<int:laptop_id>', methods=['POST'])
@login_required
def delete_laptop(laptop_id):
    laptop = Laptop.query.filter_by(id=laptop_id, user_id=current_user.id).first()
    if laptop is None:
        flash('Laptop not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('index'))

    db.session.delete(laptop)
    db.session.commit()
    flash('Laptop has been deleted.', 'success')
    return redirect(url_for('index'))

@app.route('/laptop_details/<int:laptop_id>')
@login_required
def laptop_details(laptop_id):
    laptop = Laptop.query.filter_by(id=laptop_id, user_id=current_user.id).first_or_404()
    last_reading = SensorReading.query.filter_by(laptop_id=laptop_id).order_by(db.desc(SensorReading.timestamp)).first()
    return render_template('laptop_details.html', title='Laptop Details', laptop=laptop, last_reading=last_reading)

@app.route('/api/sensor_data', methods=['POST'])
def receive_sensor_data():
    try:
        data = request.get_json()
        required = ['serial_number', 'ibeacon_rssi', 'ultrasonic_distances']
        if not all(field in data for field in required):
            return jsonify({'error': 'Missing required fields'}), 400

        laptop = Laptop.query.filter_by(serial_number=data['serial_number']).first()
        if not laptop:
            return jsonify({'error': 'Laptop not found'}), 404

        distances = data.get('ultrasonic_distances', [0.0, 0.0, 0.0, 0.0])
        new_reading = SensorReading(
            ibeacon_uuid=laptop.ibeacon_uuid,
            ibeacon_major=laptop.ibeacon_major,
            ibeacon_minor=laptop.ibeacon_minor,
            ibeacon_rssi=data['ibeacon_rssi'],
            ultrasonic_distance_1_cm=distances[0],
            ultrasonic_distance_2_cm=distances[1],
            ultrasonic_distance_3_cm=distances[2],
            ultrasonic_distance_4_cm=distances[3],
            laptop_id=laptop.id
        )

        db.session.add(new_reading)
        db.session.commit()

        # check_security_status(laptop, new_reading)  # Optional logic
        return jsonify({'message': 'Sensor data received successfully'}), 200

    except Exception as e:
        app.logger.error(f"Error processing sensor data: {e}")
        return jsonify({'error': 'Internal server error'}), 500

def check_security_status(laptop, reading):
    rssi_threshold = -80
    ultrasonic_threshold = 200

    is_out_of_range = reading.ibeacon_rssi < rssi_threshold
    is_far_away = reading.ultrasonic_distance_cm > ultrasonic_threshold

    laptop.is_stolen = is_out_of_range or is_far_away
    db.session.commit()

@app.route('/api/latest_reading/<int:laptop_id>', methods=['GET'])
@login_required
def get_latest_reading(laptop_id):
    laptop = Laptop.query.filter_by(id=laptop_id, owner=current_user).first_or_404()
    last_reading = SensorReading.query.filter_by(laptop_id=laptop.id).order_by(db.desc(SensorReading.timestamp)).first()

    if last_reading:
        return jsonify({
            'rssi': last_reading.ibeacon_rssi,
            'timestamp': last_reading.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })
    else:
        return jsonify({'rssi': 'N/A', 'timestamp': 'N/A'})

@app.route('/api/laptop_status/<string:serial_number>', methods=['POST'])
def update_laptop_status(serial_number):
    data = request.get_json()
    is_stolen = data.get('is_stolen')

    if is_stolen is None:
        return jsonify({"message": "Invalid status provided"}), 400

    laptop = Laptop.query.filter_by(serial_number=serial_number).first()
    if not laptop:
        return jsonify({"message": "Laptop not found"}), 404

    laptop.is_stolen = is_stolen
    db.session.commit()

    return jsonify({"message": f"Laptop {serial_number} stolen status updated to {is_stolen}"}), 200

@app.route('/api/laptop_status/<int:laptop_id>', methods=['GET'])
def get_laptop_status(laptop_id):
    laptop = Laptop.query.get_or_404(laptop_id)
    last_reading = laptop.readings.order_by(db.desc(SensorReading.timestamp)).first()

    return jsonify({
        "id": laptop.id,
        "serial_number": laptop.serial_number,
        "is_stolen": laptop.is_stolen,
        "last_rssi": last_reading.ibeacon_rssi if last_reading else None,
        "last_seen": last_reading.timestamp.strftime('%Y-%m-%d %H:%M:%S') if last_reading else None,
    })

@app.route('/logs')
@login_required
def logs():
    # Perform a join between the Log and Laptop tables.
    # The query retrieves the Log object and the Laptop's name for each entry.
    # It sorts by timestamp in descending order and limits to the latest 100 entries.
    logs_with_names = db.session.query(Log, Laptop.name)\
        .join(Laptop, Log.serial_number == Laptop.serial_number)\
        .order_by(db.desc(Log.timestamp))\
        .limit(100)\
        .all()
    
    # Pass the list of tuples (log_object, laptop_name) to the template.
    return render_template('logs.html', title='Event Logs', logs=logs_with_names)

@app.route('/api/log_event', methods=['POST'])
def log_event():
    data = request.get_json()
    serial_number = data.get('serial_number')
    event_type = data.get('event_type')
    
    if not serial_number or not event_type:
        return jsonify({"error": "Missing serial_number or event_type"}), 400
    
    # Define your local timezone
    local_timezone = pytz.timezone('Asia/Manila')
    
    # Get the current time and localize it
    local_now = datetime.now(local_timezone)
    
    # Create the log entry with the local timestamp
    log = Log(serial_number=serial_number, event_type=event_type, timestamp=local_now)
    db.session.add(log)
    db.session.commit()
    
    return jsonify({"success": "Log entry created"}), 201

@app.route('/toggle_sensor_script', methods=['POST'])
@login_required
def toggle_sensor_script():
    global sensor_script_process
    
    action = request.form.get('action')
    script_path = os.path.join(app.root_path, '..', 'pi_sensor_script.py')
    log_file_path = os.path.join(app.root_path, '..', 'sensor_script_log.txt')
    
    if action == 'start':
        if sensor_script_process is None or sensor_script_process.poll() is not None:
            try:
                # Use the same Python interpreter that is running Flask
                python_executable = sys.executable
                with open(log_file_path, 'a') as log_file:
                    sensor_script_process = subprocess.Popen(
                        [python_executable, script_path],
                        stdout=log_file,
                        stderr=log_file
                    )
                flash('Sensor script started successfully!', 'success')
            except Exception as e:
                flash(f'Error starting script: {e}', 'danger')
        else:
            flash('Sensor script is already running.', 'info')
    
    elif action == 'stop':
        if sensor_script_process is not None and sensor_script_process.poll() is None:
            try:
                sensor_script_process.terminate()
                sensor_script_process = None
                flash('Sensor script stopped.', 'success')
            except Exception as e:
                flash(f'Error stopping script: {e}', 'danger')
        else:
            flash('Sensor script is not running.', 'info')
            
    return redirect(url_for('index'))