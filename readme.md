# Soko Safi – Vendor Digitisation Web App

Soko Safi is a digital marketplace and business management platform designed for small merchants in Tanzania. It helps vendors manage inventory, track sales, connect with suppliers, and accept mobile money payments through a simple, mobile-first interface available in Swahili and English.

The platform also includes a buyer marketplace, supplier portal, and admin dashboard.

---

## Features

### Vendors
- Inventory management (products, pricing, stock, expiry)
- Sales and expense tracking
- Low-stock alerts
- Supplier ordering system
- Dashboard quick actions
- Reports (PDF/CSV export)
- Promotions and discounts
- Offline mode with auto-sync

### Buyers
- Product catalog with search and filters
- Product details with reviews
- Shopping cart and checkout
- Mobile money payments (M-Pesa, Tigo Pesa, Airtel Money)
- Order tracking
- Wishlist and loyalty points

### Suppliers
- Product catalog management
- Order request handling
- Supplier analytics

### Admin
- User management
- Shop and supplier verification
- Voucher system
- Training and grants management
- System logs and reports

### General
- Multi-language (Swahili / English)
- Voice input support
- Dark/light theme
- Mobile-first design
- Secure authentication and request handling

---

## Technology Stack

- Backend: Python, Flask  
- Database: SQLite (dev), PostgreSQL (prod)  
- ORM: SQLAlchemy  
- Authentication: Flask-Login  
- Frontend: Bootstrap, Chart.js  
- Security: Flask-Talisman, Bcrypt  
- PWA: Service Worker, IndexedDB  
- Deployment: Gunicorn, Nginx  

---

## Project Structure

```
soko_safi/
├── app/
│   ├── __init__.py
│   ├── extensions.py
│   ├── models.py
│   ├── forms.py
│   ├── utils.py
│   ├── decorators.py
│   ├── translations/
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   ├── sw.js
│   │   └── manifest.json
│   ├── templates/
│   │   ├── base.html
│   │   ├── auth/
│   │   ├── vendor/
│   │   ├── buyer/
│   │   ├── supplier/
│   │   └── admin/
│   └── routes/
│       ├── main.py
│       ├── auth.py
│       ├── vendor.py
│       ├── buyer.py
│       ├── supplier.py
│       ├── admin.py
│       └── api.py
├── migrations/
├── tests/
├── config.py
├── requirements.txt
├── run.py
└── README.md
```

---

## Installation

```bash
git clone https://github.com/enockdeghost/soko_safi.git
cd soko_safi

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

---

## Environment Variables (.env)



## Database Setup

```bash
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

---

## Run Application

```bash
flask run
```

Access the app at: http://127.0.0.1:5000

---

## API Overview

- POST /api/sync – Offline sync  
- GET /api/products/<shop_id> – Product list  
- GET /api/dashboard/vendor – Vendor data  
- POST /api/mobile-money/charge – Payment simulation  
- GET /api/notifications – Notifications  

---

## Contributing

1. Fork the repository  
2. Create a new branch  
3. Commit your changes  
4. Push and open a pull request  

---

## License

MIT License

---

## Contact

Website: https://sokosafi.co.tz

---

Soko Safi – Empowering local commerce.
