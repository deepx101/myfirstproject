from flask import Flask
from flask_mail import Mail, Message

app = Flask(__name__)

# Configure your SMTP server details
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'iamandeip9@gmail.com'  # Replace with your email
app.config['MAIL_PASSWORD'] = 'yulq evax sfbs fzbb'     # Replace with your app password

mail = Mail(app)

@app.route('/send_test_email')
def send_test_email():
    try:
        msg = Message(
            "Test Email from Flask",
            sender=app.config['MAIL_USERNAME'],
            recipients=["iamandeip01@gmail.com"],  # Replace with recipient email
            body="This is a test email sent from Flask app."
        )
        mail.send(msg)
        return "Test email sent successfully!"
    except Exception as e:
        return f"Error sending email: {e}"

if __name__ == '__main__':
    app.run(debug=True)