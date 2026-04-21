# 🚀 Luma ERP

Luma ERP is a cloud-based, multi-tenant ERP platform designed for apparel manufacturing companies to digitize, automate, and optimize their production workflows.

Built with a focus on real-time visibility, operational efficiency, and scalability, Luma ERP replaces fragmented Excel-based processes with a centralized system used daily by real factories.

---

## 🌍 Overview

Luma ERP is actively used by **200+ employees across 4 manufacturing factories**, supporting production, HR, and inventory operations.

The system enables:
- 📦 Real-time production tracking
- 🧵 Barcode-based workflow automation
- 👷 Employee performance monitoring
- 📊 Data-driven decision making

---

## 🧠 Key Features

### 🏭 Production Management
- Track units across cutting, sewing, and packing stages
- Barcode-based passport system for each production piece
- Real-time progress updates and defect tracking

### 👥 Employee & HR Module
- Clock-in / clock-out system with location tracking
- Performance analytics (units produced, efficiency)
- Role-based dashboards (Admin, Technologist, Employee)

### 📦 Inventory Management
- Track raw materials, rolls, and finished goods
- Monitor material consumption per production unit
- Maintain accurate stock levels across workflows

### 📊 Analytics & Reporting
- Real-time dashboards for factory operations
- Employee productivity rankings
- Production insights and defect analysis

---

## 🏗️ Architecture

- **Backend:** Python, Django (REST APIs)
- **Frontend:** Jinja2 + Vanilla JavaScript *(React version in progress)*
- **Database:** PostgreSQL
- **Storage:** AWS S3
- **Deployment:** Railway

### ⚙️ Core Concepts

- Multi-tenancy via `company_id`
- Role-based access control (7 roles)
- ACID-compliant transactional operations
- Modular architecture (Production, HR, Inventory, CRM)

---

## 🔐 Security & Data Integrity

- Strict tenant isolation (company-level data separation)
- Role-based authorization middleware
- Input validation at frontend, backend, and database levels
- Database constraints to ensure consistency

---

## ⚡ Performance & Scalability

- Optimized database queries for high-frequency operations
- Vertical scaling (current production setup)
- Future-ready for:
  - Horizontal scaling (load balancing)
  - Read replicas
  - Caching layers (Redis)
  - Advanced indexing strategies

---

## 🔄 Dev & Deployment Workflow

1. Local development & testing
2. Staging environment with dummy data
3. Production deployment
4. Continuous monitoring & iteration

- Weekly automated backups (Railway)
- Environment-based configurations (DEV / PROD)
- Error handling (403, 404, 500)

---

## 📸 Screenshots

> *(Add screenshots or demo GIFs here)*

---

## 📈 Impact

- ⏱️ Reduced manual data entry by **~60%**
- 🚀 Increased task completion speed by **~30%**
- 📊 Enabled real-time visibility across factory operations

---

## 🧪 Future Improvements

- AI-powered production analysis
- Predictive defect detection
- Advanced reporting & financial modules
- Full React frontend migration
- API integrations with external systems

---

## 🛠️ Installation (Dev)

```bash
git clone https://github.com/yourusername/luma-erp.git
cd luma-erp

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start server
python manage.py runserver