from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import base64
import io
import json
import os
from PIL import Image
import requests
import re

app = Flask(__name__, static_folder='.')
# 修正 1：更彻底的跨域配置，确保 Vercel 能够访问
CORS(app, resources={r"/*": {"origins": "*"}})

# 配置文件路径
CONFIG_FILE = 'api_config.json'

def load_config():
    """从配置文件或环境变量加载 API 配置"""
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
    if os.getenv('AI_PROVIDER'):
        config['provider'] = os.getenv('AI_PROVIDER')
    if os.getenv('AI_API_KEY'):
        config['apiKey'] = os.getenv('AI_API_KEY')
    return config

def analyze_image(image_data, mode='text', custom_prompt=''):
    """调用 AI API 分析图片"""
    config = load_config()
    if not config.get('provider') or not config.get('apiKey'):
        return {'success': False, 'error': 'API not configured'}

    provider = config['provider']
    api_key = config['apiKey']

    if 'openai' in provider.lower():
        url = 'https://api.openai.com/v1/chat/completions'
        model = 'gpt-4o'
    elif 'zhipu' in provider.lower():
        url = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
        model = 'glm-4v-flash'
    else:
        return {'success': False, 'error': f'Unsupported provider: {provider}'}

    img = Image.open(io.BytesIO(image_data))
    img.thumbnail((1024, 1024))
    if img.mode != 'RGB':
        img = img.convert('RGB')

    buffered = io.BytesIO()
    img.save(buffered, format='JPEG', quality=85)
    img_b64 = base64.b64encode(buffered.getvalue()).decode()

    if mode == 'custom' and custom_prompt:
        prompt = f"{custom_prompt}. Requirements: Within 15 words/characters, no punctuation, direct result only, no explanatory text like 'this is' or '这是'."
    elif mode == 'text':
        prompt = "Extract ONLY the main title text from this image. Rules: 1) Find the text with the LARGEST font size, 2) Output EXACTLY what you see, character by character, 3) Keep the ORIGINAL LANGUAGE unchanged, 4) Do NOT interpret, translate, or describe the content, 5) Ignore logos, small text, and subtitles. Maximum 15 characters, no punctuation."
    else:
        prompt = "Describe this illustration in English within 20 words. Focus on key visual elements, style, and composition. No punctuation."

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    payload = {
        'model': model,
        'messages': [
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{img_b64}'}}
                ]
            }
        ],
        'max_tokens': 100,
        'temperature': 0.1
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code != 200:
            return {'success': False, 'error': f'API Error: {response.text}'}
        result = response.json()['choices'][0]['message']['content'].strip()
        result = re.sub(r'[<>:"/\\|?*""、：:]', '', result)
        result = result.replace('标题是', '').replace('结果是', '').strip()
        return {'success': True, 'result': result}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# 修正 2：同时监听 /analyze 和 /api/analyze，并允许 POST 和 OPTIONS
@app.route('/analyze', methods=['POST', 'OPTIONS'])
@app.route('/api/analyze', methods=['POST', 'OPTIONS'])
def analyze():
    # 处理浏览器的预检请求
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image provided'}), 400
        image_file = request.files['image']
        mode = request.form.get('mode', 'text')
        custom_prompt = request.form.get('customPrompt', '')
        image_data = image_file.read()
        result = analyze_image(image_data, mode, custom_prompt)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config', methods=['GET', 'POST', 'OPTIONS'])
def config():
    if request.method == 'OPTIONS': return jsonify({'success': True}), 200
    if request.method == 'GET':
        config_data = load_config()
        return jsonify({
            'configured': bool(config_data.get('apiKey')),
            'provider': config_data.get('provider', '')
        })
    elif request.method == 'POST':
        try:
            data = request.json
            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

if __name__ == '__main__':
    # 修正 3：动态获取端口，确保云端兼容性
    port = int(os.environ.get("PORT", 5000))
    print(f'Design Hub Pro Server Starting on port {port}...')
    app.run(host='0.0.0.0', port=port, debug=True)
