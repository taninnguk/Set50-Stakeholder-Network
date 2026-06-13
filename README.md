# SET50 Stakeholder Network

Streamlit app สำหรับทำ Social Network Analysis จากผู้ถือหุ้นรายใหญ่ของบริษัทใน SET50/SET100 โดยใช้ Selenium เปิดเว็บไซต์ตลาดหลักทรัพย์แห่งประเทศไทยก่อน แล้วดึงข้อมูลผ่าน endpoint เดียวกับหน้าเว็บ SET

## ติดตั้ง

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

ต้องมี Chrome หรือ Edge ในเครื่อง เพราะ Selenium Manager จะหา driver ให้ตาม browser ที่เลือกในหน้า Streamlit

## รัน

```powershell
streamlit run app.py
```

ถ้า SET บล็อก request ตอนใช้ headless ให้ปิด `Headless browser` ใน sidebar แล้วลองดึงใหม่

## ข้อมูลที่ใช้

- รายชื่อหุ้นในดัชนี: `/api/set/index/{SET50|SET100}/composition`
- ผู้ถือหุ้นรายใหญ่: `/api/set/stock/{SYMBOL}/shareholder`

แอปนี้ใช้ข้อมูลเพื่อการวิเคราะห์และการศึกษา ควรตรวจสอบเงื่อนไขการใช้งานของ SET ก่อนนำไปใช้เชิงพาณิชย์หรือดึงข้อมูลปริมาณมาก
