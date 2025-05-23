# app.py
import logging
import requests
import datetime
import urllib.parse
import uuid
from typing import Any, Dict, Optional

from flask import Flask, request, render_template_string, url_for, make_response

# --- Налаштування логування ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Константи та дані областей і міст ---
NOVA_POSHTA_API_KEY = 'API KEY'
SERVICE_URLS = {
    'Нова Пошта': 'https://novaposhta.ua/',
    'Укрпошта': 'https://ukrposhta.ua/',
    'Meest': 'https://meest.com/'
}
OBLAST_CITIES = {
    'Київська': ['Київ', 'Біла Церква', 'Фастів'],
    'Львівська': ['Львів', 'Дрогобич', 'Червоноград'],
    'Одеська': ['Одеса', 'Ізмаїл', 'Чорноморськ'],
    'Дніпропетровська': ['Дніпро', 'Кривий Ріг', 'Нікополь'],
    'Харківська': ['Харків', 'Ізюм', 'Лозова']
}

# --- HTML-шаблони та CSS з JS для селекторів міст ---
BASE_STYLE = '''
<style>
  body { margin:0; padding:0; height:100vh; display:flex; align-items:center; justify-content:center;
         font-family:Arial,sans-serif; background-image:url("{{ background_url }}"); background-size:cover; }
  .overlay { background:rgba(255,255,255,0.9); padding:20px; border-radius:8px; width:600px; max-width:95%;
             box-shadow:0 0 10px rgba(0,0,0,0.2); }
  h1 { text-align:center; }
  form, .result, .error { display:flex; flex-direction:column; gap:12px; }
  label { font-size:14px; }
  select, input[type=number], input[type=date] { width:100%; padding:6px; border:1px solid #ccc; border-radius:4px; }
  .row { display:flex; gap:10px; }
  .row > div { flex:1; }
  table { width:100%; border-collapse: collapse; margin-top:10px; }
  th, td { border:1px solid #ccc; padding:8px; text-align:center; }
  .buttons { display:flex; justify-content:center; gap:10px; margin-top:10px; }
  .buttons a, button { padding:8px 16px; background:#007BFF; color:white; border:none; border-radius:4px; cursor:pointer; text-decoration:none; }
  .buttons a:hover, button:hover { background:#0056b3; }
</style>
<script>
const oblastCities = {{ oblast_cities | safe }};
function updateCities(prefix) {
  const oblast = document.getElementById(prefix + '_oblast').value;
  const citySelect = document.getElementById(prefix + '_city');
  citySelect.innerHTML = '';
  oblastCities[oblast].forEach(c => {
    const opt = document.createElement('option'); opt.value = c; opt.text = c;
    citySelect.appendChild(opt);
  });
}
window.addEventListener('DOMContentLoaded', () => {
  ['sender','receiver'].forEach(prefix => updateCities(prefix));
});
</script>
''' 

HTML_FORM = BASE_STYLE + '''
<div class="overlay">
  <h1>Порівняння доставок</h1>
  <form method="post" action="/compare">
    <div class="row">
      <div>
        <label>Область відправника:<br>
          <select id="sender_oblast" name="sender_oblast" onchange="updateCities('sender')">
            {% for oblast in oblast_cities.keys() %}
            <option value="{{ oblast }}">{{ oblast }}</option>
            {% endfor %}
          </select>
        </label>
      </div>
      <div>
        <label>Місто відправника:<br>
          <select id="sender_city" name="sender" required></select>
        </label>
      </div>
    </div>
    <div class="row">
      <div>
        <label>Область отримувача:<br>
          <select id="receiver_oblast" name="receiver_oblast" onchange="updateCities('receiver')">
            {% for oblast in oblast_cities.keys() %}
            <option value="{{ oblast }}">{{ oblast }}</option>
            {% endfor %}
          </select>
        </label>
      </div>
      <div>
        <label>Місто отримувача:<br>
          <select id="receiver_city" name="receiver" required></select>
        </label>
      </div>
    </div>
    <label>Вага (кг):<br><input type="number" step="any" min="0" name="weight" required></label>
    <label>Дата відправлення:<br><input type="date" name="date" required></label>
    <div class="row">
      <div>
        <label>Метод відправлення:<br>
          <select name="send_mode">
            <option value="Warehouse">Відділення</option>
            <option value="Door">Кур’єр забере з дому</option>
          </select>
        </label>
      </div>
      <div>
        <label>Метод отримання:<br>
          <select name="receive_mode">
            <option value="Warehouse">Відділення</option>
            <option value="Door">Кур’єр доставить додому</option>
          </select>
        </label>
      </div>
    </div>
    <div class="buttons">
      <label><input type="radio" name="option" value="Найдешевший" checked> Найдешевший</label>
      <label><input type="radio" name="option" value="Найшвидший"> Найшвидший</label>
      <label><input type="radio" name="option" value="Оптимальний"> Оптимальний</label>
    </div>
    <div class="buttons"><button type="submit">Порівняти</button></div>
  </form>
</div>
'''

RESULT_TEMPLATE = BASE_STYLE + '''
<div class="overlay result">
  <h1>Результати порівняння</h1>
  <table>
    <thead><tr><th>Служба</th><th>Ціна, грн</th><th>Час, дн.</th><th>Замовити</th></tr></thead>
    <tbody>
      {% for e in estimates %}
      <tr>
        <td>{{ e.service }}</td><td>{{ e.price }}</td><td>{{ e.time }}</td>
        <td><a href="{{ service_urls[e.service] }}" target="_blank">Перейти</a></td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <p style="text-align:center;"><strong>Найкращий:</strong> {{ best.service }} — {{ best.price }} грн, {{ best.time }} дн.</p>
  <p style="text-align:center;">Від: {{ sender }}, До: {{ receiver }}</p>
  <div class="buttons">
    <a href="/">Нова спроба</a>
  </div>
</div>
'''

ERROR_TEMPLATE = BASE_STYLE + '''
<div class="overlay error">
  <h1>Помилка</h1>
  <p>{{ message }}</p>
  <div class="buttons"><a href="/">Назад</a></div>
</div>
'''

# --- Обчислювальні функції ---
def search_city(city_name: str) -> Optional[str]:
    try:
        resp = requests.post('https://api.novaposhta.ua/v2.0/json/', json={
            'apiKey': NOVA_POSHTA_API_KEY,
            'modelName': 'Address',
            'calledMethod': 'getCities',
            'methodProperties': {'FindByString': city_name, 'Limit': 1}
        }).json().get('data', [])
        return resp[0]['Ref'] if resp else None
    except Exception as e:
        logger.error("City search error: %s", e)
        return None


def get_nova_poshta_estimate(data: Dict[str, Any], service_type: str) -> Optional[float]:
    try:
        payload = {
            'apiKey': NOVA_POSHTA_API_KEY,
            'modelName': 'InternetDocument',
            'calledMethod': 'getDocumentPrice',
            'methodProperties': {
                'CitySender': data['sender_ref'],
                'CityRecipient': data['receiver_ref'],
                'Weight': data['weight'],
                'ServiceType': service_type,
                'Cost': '500',
                'CargoType': 'Cargo',
            },
        }
        resp = requests.post('https://api.novaposhta.ua/v2.0/json/', json=payload).json()
        cost = resp.get('data', [{}])[0].get('Cost')
        return float(cost) if cost else None
    except Exception as e:
        logger.error("Nova Poshta error: %s", e)
        return None


def get_ukrposhta_estimate(data: Dict[str, Any], send_mode: str, receive_mode: str) -> float:
    base = round(35 + 5 * data['weight'], 2)
    surcharge = 20 if (send_mode=='Door' or receive_mode=='Door') else 0
    return base + surcharge


def get_meest_estimate(data: Dict[str, Any], send_mode: str, receive_mode: str) -> float:
    base = round(30 + 6 * data['weight'], 2)
    surcharge = 20 if (send_mode=='Door' or receive_mode=='Door') else 0
    return base + surcharge

# --- Flask-додаток ---
app = Flask(__name__)

@app.context_processor
def inject_background():
    return dict(background_url=url_for('static', filename='background.jpg'))

@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML_FORM, oblast_cities=OBLAST_CITIES)

@app.route("/compare", methods=["POST"])
def compare():
    sender = request.form.get('sender')
    receiver = request.form.get('receiver')
    send_mode = request.form.get('send_mode','Warehouse')
    receive_mode = request.form.get('receive_mode','Warehouse')
    # Перевірка ваги
    try:
        weight = float(request.form.get('weight','0'))
        if weight < 0:
            raise ValueError('negative')
    except ValueError:
        return render_template_string(ERROR_TEMPLATE, message="Вага не може бути від'ємною."), 400
    # Перевірка дати
    date_str = request.form.get('date','')
    try:
        send_date = datetime.datetime.strptime(date_str,'%Y-%m-%d').date()
        if send_date < datetime.date.today(): raise ValueError
    except ValueError:
        return render_template_string(ERROR_TEMPLATE, message="Некоректна дата."), 400
    # Пошук Ref міст
    sender_ref = search_city(sender)
    receiver_ref = search_city(receiver)
    data = {'sender_ref': sender_ref, 'receiver_ref': receiver_ref, 'weight': weight}
    # Визначення типу сервісу для Nova Poshta
    mapping = {
        ('Warehouse','Warehouse'):'WarehouseWarehouse',
        ('Warehouse','Door'):'WarehouseDoors',
        ('Door','Warehouse'):'DoorsWarehouse',
        ('Door','Door'):'DoorsDoors',
    }
    service_type = mapping.get((send_mode, receive_mode), 'WarehouseDoors')
    # Обрахунок варіантів
    estimates = []
    np_price = get_nova_poshta_estimate(data, service_type)
    if np_price is not None:
        estimates.append({'service':'Нова Пошта','price':np_price,'time':2})
    estimates.append({'service':'Укрпошта','price':get_ukrposhta_estimate(data,send_mode,receive_mode),'time':5})
    estimates.append({'service':'Meest','price':get_meest_estimate(data,send_mode,receive_mode),'time':4})
    # Вибір найкращого
    option = request.form.get('option','Найдешевший')
    if option=='Найдешевший':
        best = min(estimates, key=lambda x: x['price'])
    elif option=='Найшвидший':
        best = min(estimates, key=lambda x: x['time'])
    else:
        best = min(estimates, key=lambda x: x['price']*x['time'])
    # Підготовка посилань
    url = SERVICE_URLS.get(best['service'], '')
    summary = urllib.parse.quote(f"Відправити посилку: {sender} → {receiver}")
    return render_template_string(
        RESULT_TEMPLATE,
        sender=sender,
        receiver=receiver,
        estimates=estimates,
        best=best,
        service_urls=SERVICE_URLS
    )

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
