from flask import render_template, request, flash, redirect, url_for, current_app
from flask_mail import Message
from app.routes import main_bp as bp
from app.extensions import mail

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/about')
def about():
    return render_template('about.html')

@bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        try:
            msg = Message(
                subject=f"Soko Safi Contact Form: Message from {name}",
                recipients=[current_app.config['MAIL_RECIPIENT']],
                reply_to=email,
                body=f"Name: {name}\nEmail: {email}\n\nMessage:\n{message}"
            )
            mail.send(msg)
            flash('Asante kwa ujumbe wako. Tutawasiliana nawe hivi karibuni.', 'success')
        except Exception as e:
            current_app.logger.error(f"Email sending failed: {e}")
            flash('Samahani, kuna tatizo la kiufundi. Tafadhali jaribu tena baadaye.', 'danger')
        return redirect(url_for('main.contact'))
    return render_template('contact.html')