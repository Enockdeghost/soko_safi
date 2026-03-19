from flask import Blueprint

main_bp = Blueprint('main', __name__)
auth_bp = Blueprint('auth', __name__)
vendor_bp = Blueprint('vendor', __name__)
supplier_bp = Blueprint('supplier', __name__)
admin_bp = Blueprint('admin', __name__)
api_bp = Blueprint('api', __name__)
buyer_bp = Blueprint('buyer', __name__)

from . import main, auth, vendor, supplier, admin, api, buyer