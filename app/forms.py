from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, FloatField, SelectField, DateField, BooleanField, TextAreaField, SubmitField, IntegerField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Length, Optional, NumberRange
from app.models import User
import phonenumbers
from datetime import date

class LoginForm(FlaskForm):
    phone = StringField('Namba ya Simu', validators=[DataRequired()])
    password = PasswordField('Nenosiri', validators=[DataRequired()])
    remember = BooleanField('Nikumbuke')
    submit = SubmitField('Ingia')

class RegistrationForm(FlaskForm):
    phone = StringField('Namba ya Simu', validators=[DataRequired()])
    full_name = StringField('Jina Kamili', validators=[DataRequired(), Length(min=2, max=100)])
    password = PasswordField('Nenosiri', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Rudia Nenosiri', validators=[DataRequired(), EqualTo('password')])
    role = SelectField('Wewe ni nani?', choices=[('vendor', 'Mfanyabiashara'), ('supplier', 'Msambazaji'), ('buyer', 'Mnunuzi')])
    submit = SubmitField('Jisajili')

    def validate_phone(self, phone):
        try:
            p = phonenumbers.parse(phone.data, 'TZ')
            if not phonenumbers.is_valid_number(p):
                raise ValidationError('Namba ya simu si sahihi.')
        except:
            raise ValidationError('Namba ya simu si sahihi.')
        user = User.query.filter_by(phone=phone.data).first()
        if user is not None:
            raise ValidationError('Namba hii tayari imesajiliwa.')

class ChangePasswordForm(FlaskForm):
    old_password = PasswordField('Nenosiri la Zamani', validators=[DataRequired()])
    new_password = PasswordField('Nenosiri Jipya', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Rudia Nenosiri Jipya', validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('Badilisha')

class ShopSetupForm(FlaskForm):
    name = StringField('Jina la Duka', validators=[DataRequired(), Length(max=100)])
    location = StringField('Mahali', validators=[DataRequired(), Length(max=200)])
    category = SelectField('Aina ya Biashara', choices=[('duka', 'Duka la rejareja'), ('kiosk', 'Kioski'), ('stall', 'Soko'), ('other', 'Nyingine')])
    submit = SubmitField('Hifadhi')

class ProductForm(FlaskForm):
    name = StringField('Jina la Bidhaa', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Maelezo', validators=[Optional(), Length(max=500)])
    price = FloatField('Bei (TZS)', validators=[DataRequired(), NumberRange(min=0)])
    quantity = FloatField('Idadi / Uzito', validators=[DataRequired(), NumberRange(min=0)])
    unit = SelectField('Kipimo', choices=[('pcs', 'Kipande'), ('kg', 'Kilo'), ('bunch', 'Fungu'), ('litre', 'Lita')])
    category_id = SelectField('Aina ya Bidhaa', coerce=int, validators=[Optional()])
    image_url = StringField('Kiungo cha Picha (URL)', validators=[Optional()])
    expiry_date = DateField('Tarehe ya Kuisha', validators=[Optional()])
    low_stock_threshold = FloatField('Onyesha ikiwa chini ya', default=5, validators=[NumberRange(min=0)])
    submit = SubmitField('Hifadhi')

class SaleForm(FlaskForm):
    product_id = SelectField('Bidhaa', coerce=int, validators=[DataRequired()])
    quantity = FloatField('Idadi', validators=[DataRequired(), NumberRange(min=0.01)])
    payment_method = SelectField('Njia ya Malipo', choices=[('cash', 'Cash'), ('mpesa', 'M-Pesa'), ('tigo', 'TigoPesa'), ('airtel', 'Airtel Money')])
    submit = SubmitField('Rekodi Mauzo')

class ExpenseForm(FlaskForm):
    category_id = SelectField('Aina ya Gharama', coerce=int, validators=[DataRequired()])
    amount = FloatField('Kiasi (TZS)', validators=[DataRequired(), NumberRange(min=0)])
    description = StringField('Maelezo', validators=[Optional(), Length(max=200)])
    date = DateField('Tarehe', default=date.today, validators=[DataRequired()])
    submit = SubmitField('Weka')

class ExpenseCategoryForm(FlaskForm):
    name = StringField('Jina la Aina', validators=[DataRequired(), Length(max=50)])
    submit = SubmitField('Ongeza')

class OrderRequestForm(FlaskForm):
    supplier_id = SelectField('Msambazaji', coerce=int, validators=[DataRequired()])
    product_name = StringField('Jina la Bidhaa', validators=[DataRequired(), Length(max=100)])
    quantity = FloatField('Idadi', validators=[DataRequired(), NumberRange(min=0.01)])
    unit = SelectField('Kipimo', choices=[('pcs', 'Kipande'), ('kg', 'Kilo'), ('bunch', 'Fungu'), ('litre', 'Lita')])
    submit = SubmitField('Tuma Ombi')

class GrantApplicationForm(FlaskForm):
    amount = FloatField('Kiasi Unachoomba (TZS)', validators=[DataRequired(), NumberRange(min=1000)])
    purpose = TextAreaField('Sababu ya Ombi', validators=[DataRequired(), Length(max=500)])
    business_plan = TextAreaField('Mpango wa Biashara (au kiungo cha sauti)', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('Tuma Ombi')

class SupplierProfileForm(FlaskForm):
    business_name = StringField('Jina la Biashara', validators=[DataRequired(), Length(max=100)])
    contact_phone = StringField('Namba ya Simu ya Mawasiliano', validators=[Optional()])
    location = StringField('Mahali', validators=[Optional(), Length(max=200)])
    submit = SubmitField('Hifadhi')

class SupplierProductForm(FlaskForm):
    name = StringField('Jina la Bidhaa', validators=[DataRequired(), Length(max=100)])
    price = FloatField('Bei (TZS)', validators=[Optional(), NumberRange(min=0)])
    unit = SelectField('Kipimo', choices=[('pcs', 'Kipande'), ('kg', 'Kilo'), ('bunch', 'Fungu'), ('litre', 'Lita')])
    submit = SubmitField('Hifadhi')

class VoucherForm(FlaskForm):
    amount = FloatField('Kiasi (TZS)', validators=[DataRequired(), NumberRange(min=100)])
    beneficiary_name = StringField('Jina la Mnufaika', validators=[Optional(), Length(max=100)])
    beneficiary_phone = StringField('Namba ya Simu ya Mnufaika', validators=[Optional()])
    expiry_date = DateField('Tarehe ya Kuisha', validators=[Optional()])
    submit = SubmitField('Unda Vocha')

    def validate_beneficiary_phone(self, phone):
        if phone.data:
            try:
                p = phonenumbers.parse(phone.data, 'TZ')
                if not phonenumbers.is_valid_number(p):
                    raise ValidationError('Namba ya simu si sahihi.')
            except:
                raise ValidationError('Namba ya simu si sahihi.')

class BulkVoucherForm(FlaskForm):
    count = IntegerField('Idadi ya Vocha', validators=[DataRequired(), NumberRange(min=1, max=100)])
    amount = FloatField('Kiasi kwa kila Vocha (TZS)', validators=[DataRequired(), NumberRange(min=100)])
    expiry_date = DateField('Tarehe ya Kuisha (si lazima)', validators=[Optional()])
    submit = SubmitField('Unda Vocha Nyingi')

class TrainingProgramForm(FlaskForm):
    title = StringField('Jina la Mafunzo', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Maelezo', validators=[Optional(), Length(max=500)])
    start_date = DateField('Tarehe ya Kuanza', validators=[DataRequired()])
    end_date = DateField('Tarehe ya Kumaliza', validators=[DataRequired()])
    capacity = IntegerField('Upeo wa Washiriki', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Hifadhi')

class UserEditForm(FlaskForm):
    full_name = StringField('Jina Kamili', validators=[Optional(), Length(max=100)])
    role = SelectField('Wajibu', choices=[('vendor', 'Mfanyabiashara'), ('supplier', 'Msambazaji'), ('buyer', 'Mnunuzi'), ('admin', 'Admin')])
    is_active = BooleanField('Akaunti Inatumika')
    submit = SubmitField('Sasisha')

class DateRangeForm(FlaskForm):
    start_date = DateField('Kuanzia', validators=[DataRequired()])
    end_date = DateField('Mpaka', validators=[DataRequired()])
    submit = SubmitField('Chuja')

    def validate_end_date(self, end_date):
        if end_date.data < self.start_date.data:
            raise ValidationError('Tarehe ya mwisho ni lazima iwe baada ya tarehe ya kuanza.')