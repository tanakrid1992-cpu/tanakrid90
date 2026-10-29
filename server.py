import json
import os
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

PAGE = """<!doctype html>
<html lang="th">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ระบบเช็คอินพนักงาน</title>
<style>
body{font-family:system-ui;background:#eef5f4;color:#173e36;
max-width:760px;margin:40px auto;padding:20px}
section{background:white;padding:24px;border-radius:16px;margin:20px 0}
input,button{font:inherit;padding:12px;border-radius:8px}
input{box-sizing:border-box;width:100%;margin:12px 0}
button{background:#167565;color:white;border:0;cursor:pointer}
button:disabled{opacity:.5}
td,th{padding:12px;text-align:left;border-bottom:1px solid #ddd}
table{width:100%;border-collapse:collapse}
</style>
<h1>ระบบเช็คอินพนักงาน</h1>
<p>บันทึกเวลาเข้า–ออกบน Supabase</p>
<section>
<form id="form">
<label for="name">ชื่อ–นามสกุล</label>
<input id="name" required maxlength="100" autocomplete="name">
<button type="submit" value="in">เช็คอินเข้างาน</button>
<button type="submit" value="out">เช็คเอาต์ออกงาน</button>
</form>
<p id="message" role="status"></p>
</section>
<section>
<h2>รายการล่าสุด</h2>
<p>แสดงสูงสุด 100 รายการ · เวลาไทย</p>
<table>
<thead><tr><th>ชื่อ</th><th>สถานะ</th><th>เวลา</th></tr></thead>
<tbody id="rows"></tbody>
</table>
</section>
<script>
const el = id => document.getElementById(id);

async function api(options) {
  const response = await fetch('/api/checkins', options);
  const data = await response.json();
  if (!response.ok) throw Error(data.error || 'เชื่อมต่อไม่สำเร็จ');
  return data;
}

async function refresh() {
  const records = await api();
  el('rows').replaceChildren();
  for (const record of records) {
    const row = document.createElement('tr');
    const values = [
      record.name,
      record.action === 'in' ? 'เข้างาน' : 'ออกงาน',
      new Date(record.created_at).toLocaleString(
        'th-TH', {timeZone: 'Asia/Bangkok'}
      )
    ];
    for (const value of values) {
      const cell = document.createElement('td');
      cell.textContent = value;
      row.append(cell);
    }
    el('rows').append(row);
  }
}

el('form').addEventListener('submit', async event => {
  event.preventDefault();
  const action = event.submitter.value;
  const buttons = document.querySelectorAll('button');
  buttons.forEach(button => button.disabled = true);
  el('message').textContent = 'กำลังบันทึก…';
  try {
    await api({
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: el('name').value, action})
    });
    el('message').textContent = 'บันทึกสำเร็จ';
    try {
      await refresh();
    } catch {
      el('message').textContent =
        'บันทึกสำเร็จ แต่โหลดรายการไม่ได้ กรุณารีเฟรชหน้า';
    }
  } catch (error) {
    el('message').textContent = error.message;
  } finally {
    buttons.forEach(button => button.disabled = false);
  }
});

refresh().catch(error => {
  el('message').textContent = error.message;
});
</script>
</html>"""


def database(record=None):
    endpoint = URL + "/rest/v1/checkins"
    if record is None:
        endpoint += "?select=*&order=created_at.desc&limit=100"
    request = urllib.request.Request(
        endpoint,
        data=None if record is None else json.dumps(record).encode(),
        headers={
            "apikey": KEY,
            "Authorization": "Bearer " + KEY,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, data, html=False):
        body = data.encode() if html else json.dumps(
            data, ensure_ascii=False
        ).encode()
        self.send_response(status)
        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8"
            if html else "application/json; charset=utf-8",
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            return self.respond(200, PAGE, html=True)
        if self.path != "/api/checkins":
            return self.respond(404, {"error": "ไม่พบหน้า"})
        try:
            self.respond(200, database())
        except Exception:
            self.respond(503, {"error": "อ่านฐานข้อมูลไม่สำเร็จ"})

    def do_POST(self):
        if self.path != "/api/checkins":
            return self.respond(404, {"error": "ไม่พบหน้า"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError()
            data = json.loads(self.rfile.read(length))
            name = data.get("name", "")
            action = data.get("action")
            if not isinstance(name, str):
                raise ValueError()
            name = name.strip()
            if not 1 <= len(name) <= 100 or action not in ("in", "out"):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            return self.respond(400, {"error": "กรอกชื่อและเลือกเข้า–ออก"})
        try:
            result = database({
                "name": name,
                "action": action,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            self.respond(201, result[0])
        except Exception:
            self.respond(503, {"error": "บันทึกไม่สำเร็จ กรุณาลองใหม่"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
