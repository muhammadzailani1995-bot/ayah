from flask import Flask, request, render_template_string, jsonify
import time, hmac, hashlib, requests, os
from dotenv import load_dotenv

# === LOAD ENV ===
load_dotenv()

app = Flask(__name__)

PARTNER_ID = int(os.getenv("PARTNER_ID"))
PARTNER_KEY = os.getenv("PARTNER_KEY")
SHOP_ID = int(os.getenv("SHOP_ID"))
SMS_API_KEY = os.getenv("SMS_API_KEY")
COUNTRY_CODE = int(os.getenv("COUNTRY_CODE", 6))

# Mapping produk Shopee ke service SMS-Activate
SERVICE_MAP = {
    "zus": "aik",
    "kfc": "fz",
    "chagee": "bwx",
    "tealive": "avb"
}

# === HTML ===
HTML_FORM = """
<!DOCTYPE html>
<html>
<head>
  <title>Redeem Virtual Number</title>
  <script>
    let activationId = null;

    function checkOTP() {
      if (activationId) {
        fetch("/check_otp?id=" + activationId)
          .then(r => r.json())
          .then(data => {
            if (data.code) {
              document.getElementById("otp").innerText = "Kod OTP: " + data.code;
            } else {
              document.getElementById("otp").innerText = "Sedang tunggu OTP...";
            }
          })
          .catch(err => {
            document.getElementById("otp").innerText = "Ralat semak OTP!";
          });
      }
    }
    setInterval(checkOTP, 15000); // auto check setiap 15 saat
  </script>
</head>
<body>
  <h2>Masukkan Order ID Shopee</h2>
  <form method="POST">
    <input type="text" name="order_sn" placeholder="Order ID" required>
    <button type="submit">Redeem</button>
  </form>

  {% if product %}
    <h3>Produk: {{ product }}</h3>
  {% endif %}

  {% if number %}
    <h3>Nombor Anda: {{ number }}</h3>
    <p id="otp">Sedang tunggu OTP...</p>
    <script>
      activationId = "{{ activation_id }}";
      checkOTP();
    </script>
  {% endif %}

  {% if error %}
    <p style="color:red">{{ error }}</p>
  {% endif %}
</body>
</html>
"""

# === SIGNATURE SHOPEE ===
def make_signature(path, timestamp):
    base_string = f"{PARTNER_ID}{path}{timestamp}"
    return hmac.new(
        PARTNER_KEY.encode(),
        base_string.encode(),
        hashlib.sha256
    ).hexdigest()

# === CHECK ORDER ===
def check_order(order_sn):
    path = "/api/v2/order/get_order_detail"
    url = "https://partner.shopeemobile.com" + path
    timestamp = int(time.time())
    sign = make_signature(path, timestamp)

    payload = {
        "partner_id": PARTNER_ID,
        "shop_id": SHOP_ID,
        "timestamp": timestamp,
        "sign": sign,
        "order_sn_list": [order_sn]
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

# === GET NUMBER ===
def get_virtual_number(service, country=COUNTRY_CODE):
    url = f"https://api.sms-activate.org/stubs/handler_api.php?api_key={SMS_API_KEY}&action=getNumber&service={service}&country={country}"
    try:
        r = requests.get(url, timeout=10).text
        parts = r.split(":")
        if parts[0] == "ACCESS_NUMBER":
            return {"id": parts[1], "number": parts[2]}
        return None
    except Exception:
        return None

# === GET OTP ===
def get_status(activation_id):
    url = f"https://api.sms-activate.org/stubs/handler_api.php?api_key={SMS_API_KEY}&action=getStatus&id={activation_id}"
    try:
        r = requests.get(url, timeout=10).text
        if r.startswith("STATUS_OK"):
            return r.split(":")[1]
        return None
    except Exception:
        return None

@app.route("/", methods=["GET", "POST"])
def redeem():
    number, error, activation_id, product = None, None, None, None

    if request.method == "POST":
        order_sn = request.form["order_sn"]
        order_info = check_order(order_sn)

        if order_info.get("error") == "" and "response" in order_info:
            try:
                product_name = order_info["response"]["order_list"][0]["item_list"][0]["item_name"].lower()
                product = product_name

                # cari service code
                service_code = None
                for key, val in SERVICE_MAP.items():
                    if key in product_name:
                        service_code = val
                        break

                if service_code:
                    vnum = get_virtual_number(service=service_code)
                    if vnum:
                        number = vnum["number"]
                        activation_id = vnum["id"]
                    else:
                        error = "Gagal tempah nombor (tiada nombor tersedia)."
                else:
                    error = f"Produk '{product_name}' tiada dalam mapping."
            except Exception as e:
                error = f"Ralat proses order: {e}"
        else:
            error = f"Gagal dapatkan maklumat order: {order_info.get('message', 'Tidak diketahui')}"

    return render_template_string(HTML_FORM, product=product, number=number, activation_id=activation_id, error=error)

@app.route("/check_otp")
def check_otp():
    activation_id = request.args.get("id")
    otp = get_status(activation_id)
    return jsonify({"code": otp})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
