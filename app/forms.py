from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, IntegerField, SelectField
from wtforms.validators import DataRequired, ValidationError, Email, EqualTo, Length, AnyOf
from app.models import User, Laptop

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email address.')
        
class LaptopForm(FlaskForm):
    name = StringField('Laptop Name', validators=[DataRequired(), Length(min=1, max=120)])
    serial_number = StringField('Serial Number', validators=[DataRequired(), Length(min=1, max=120)])
    
    # Holyiot iBeacon fields
    ibeacon_uuid = StringField('iBeacon UUID', validators=[DataRequired()])
    ibeacon_major = IntegerField('iBeacon Major', validators=[DataRequired()])
    ibeacon_minor = IntegerField('iBeacon Minor', validators=[DataRequired()])
    
    # Add this new field for the ultrasonic sensor
    ultrasonic_sensor_index = SelectField(
        'Assign Ultrasonic Sensor',
        validators=[AnyOf([0, 1, 2, 3], message='Please select an ultrasonic sensor.')],
        coerce=int,
        choices=[(0, 'Sensor 0'), (1, 'Sensor 1'), (2, 'Sensor 2'), (3, 'Sensor 3')]
    )
    
    submit = SubmitField('Add Laptop')

    def validate_serial_number(self, serial_number):
        laptop = Laptop.query.filter_by(serial_number=serial_number.data).first()
        if laptop is not None:
            raise ValidationError('A laptop with this serial number already exists.')