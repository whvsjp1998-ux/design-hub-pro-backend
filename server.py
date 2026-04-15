from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import base64
import io
import json
import os
from PIL import Image
import requests

app = Flask(__name__, static_folder='.')
CORS(app)

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

    # 根据服务商设置 API 端点
    if 'openai' in provider.lower():
        url = 'https://api.openai.com/v1/chat/completions'
        model = 'gpt-4o'
    elif 'zhipu' in provider.lower():
        url = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
        model = 'glm-4v-flash'
    else:
        return {'success': False, 'error': f'Unsupported provider: {provider}'}

    # 压缩图片
    img = Image.open(io.BytesIO(image_data))
    img.thumbnail((1024, 1024))
    if img.mode != 'RGB':
        img = img.convert('RGB')

    buffered = io.BytesIO()
    img.save(buffered, format='JPEG', quality=85)
    img_b64 = base64.b64encode(buffered.getvalue()).decode()

    # 构建提示词
    if mode == 'custom' and custom_prompt:
        # 自定义模式：根据用户输入的语言决定输出语言
        prompt = f"{custom_prompt}. Requirements: Within 15 words/characters, no punctuation, direct result only, no explanatory text like 'this is' or '这是'."
    elif mode == 'text':
        # 图像标题模式：找到画面中最突出、最显眼的标题并提取
        prompt = "Extract ONLY the main title text from this image. Rules: 1) Find the text with the LARGEST font size, 2) Output EXACTLY what you see, character by character, 3) Keep the ORIGINAL LANGUAGE unchanged, 4) Do NOT interpret, translate, or describe the content, 5) Ignore logos, small text, and subtitles. Maximum 15 characters, no punctuation."
    else:  # image mode
        # 插图细节提取模式：默认用英文描述
        prompt = "Describe this illustration in English within 20 words. Focus on key visual elements, style, and composition. No punctuation."

    # 调用 API
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
        # 清理结果
        import re
        result = re.sub(r'[<>:"/\\|?*""、：:]', '', result)
        result = result.replace('标题是', '').replace('结果是', '').strip()

        return {'success': True, 'result': result}

    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/api/analyze', methods=['POST'])
def analyze():
    """单张图片识别接口"""
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

@app.route('/api/config', methods=['GET', 'POST'])
def config():
    """API 配置接口"""
    if request.method == 'GET':
        config_data = load_config()
        # 不返回完整的 API Key，只返回是否已配置
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
    """主页"""
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """提供静态文件"""
    return send_from_directory('.', path)

if __name__ == '__main__':
    print('Design Hub Pro Server Starting...')
    print('Server running at: http://localhost:5000')
    print('Press Ctrl+C to stop')
    app.run(host='0.0.0.0', port=5000, debug=True)
