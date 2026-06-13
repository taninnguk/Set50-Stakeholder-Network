# SET50 Stakeholder Network

Streamlit app สำหรับทำ Social Network Analysis จากผู้ถือหุ้นรายใหญ่ของบริษัทใน SET50/SET100 โดยใช้ Selenium เปิดเว็บไซต์ตลาดหลักทรัพย์แห่งประเทศไทยก่อน แล้วดึงข้อมูลผ่าน endpoint เดียวกับหน้าเว็บ SET

## ติดตั้ง

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

ต้องมี Chrome ในเครื่อง เพราะแอปใช้ Selenium แบบ Chrome headless เป็นค่า default

## รัน

```powershell
streamlit run app.py
```

หน้าแรกจะแสดง default snapshot จาก `data/default_shareholders.csv` ทันที โดยไม่ต้องกดดึงข้อมูลก่อน หากต้องการข้อมูลล่าสุดให้ใช้ปุ่ม `ดึงข้อมูลและสร้างกราฟ` ใน sidebar

การดึงข้อมูลสดจาก sidebar จะใช้ Chrome headless ตามค่า default ของแอป

## อัปเดต Default Snapshot

```powershell
python scripts\build_default_data.py --index SET50 --top-n 5 --limit 50 --lang th
```

คำสั่งนี้จะดึงข้อมูลจาก SET ผ่าน Selenium และเขียนทับ `data/default_shareholders.csv`
ถ้าต้องการเปิด browser ให้เห็นระหว่างอัปเดต snapshot ให้เติม `--headed`

## ข้อมูลที่ใช้

- รายชื่อหุ้นในดัชนี: `/api/set/index/{SET50|SET100}/composition`
- ผู้ถือหุ้นรายใหญ่: `/api/set/stock/{SYMBOL}/shareholder`

แอปนี้ใช้ข้อมูลเพื่อการวิเคราะห์และการศึกษา ควรตรวจสอบเงื่อนไขการใช้งานของ SET ก่อนนำไปใช้เชิงพาณิชย์หรือดึงข้อมูลปริมาณมาก
