# Laptop Security App

## Description

The Laptop Security App is a web application built with Flask that allows you to monitor the security of your laptops using iBeacon and ultrasonic sensor data. The app tracks the proximity of registered laptops and alerts you if a laptop is moved beyond a safe distance.

## Features

* **User Authentication:** Secure user registration and login.
* **Laptop Management:** Add, view, and delete laptops with their serial numbers.
* **iBeacon Tagging:** Associate a Holyiot iBeacon tag with each laptop.
* **Real-time Monitoring:** Receives and processes sensor data from a Raspberry Pi.
* **RSSI Tracking:** Monitors the Received Signal Strength Indicator (RSSI) of the iBeacon.
* **Ultrasonic Distance:** Tracks the distance of the laptop from a secure location.
* **Security Status:** Automatically marks a laptop as 'stolen' if it is moved too far.

---

## Installation

### Prerequisites

* Python 3.8+
* pip (Python package installer)
* A running PostgreSQL database

### Setup

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/arvndlr/laptop-security-application.git](https://github.com/arvndlr/laptop-security-application.git)
    cd laptop-security-application
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    Before installing the app's dependencies, you may need to install `python3-dev` to build some of the required Python packages.

    ```bash
    sudo apt update
    sudo apt install python3-dev
    pip install -r requirements.txt
    ```

---

### 4. Setting up the PostgreSQL Database

These steps will install PostgreSQL, create a dedicated user and database for your application, and configure the necessary permissions.

1.  **Install PostgreSQL:**
    ```bash
    sudo apt install postgresql
    ```

2.  **Access the PostgreSQL shell:**
    ```bash
    sudo -i -u postgres
    ```

3.  **Create a database user and database:**
    Enter a password when prompted for the new user.
    ```bash
    createuser --pwprompt justine
    createdb -O justine laptop_security_db
    ```
    **Note:** The `justine` username and `laptop_security_db` database name should match what's in your application's configuration.

4.  **Grant permissions on the schema:**
    Enter the `psql` command-line interface to grant permissions, then exit.
    ```bash
    psql -d laptop_security_db
    ```
    At the `psql` prompt, run:
    ```sql
    GRANT ALL PRIVILEGES ON SCHEMA public TO justine;
    \q
    ```

5.  **Exit the `postgres` user shell:**
    ```bash
    exit
    ```

6.  **Update the `SQLALCHEMY_DATABASE_URI`:**
    Open your `config.py` file and update the `SQLALCHEMY_DATABASE_URI` to use your new PostgreSQL database.
    ```python
    SQLALCHEMY_DATABASE_URI = 'postgresql://justine:your_password@localhost/laptop_security_db'
    ```

7.  **Initialize the database:**
    ```bash
    flask db upgrade
    ```

---

### 5. Run the application:
```bash
python run.py
