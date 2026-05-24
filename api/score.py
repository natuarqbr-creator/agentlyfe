from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)

        offer = data.get('offer', '')
        places = data.get('places', [])

        api_key = os.environ.get('OPENAI_API_KEY', '')
        if not api_key:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'OPENAI_API_KEY not configured'}).encode())
            return

        try:
            # Build places summary for the prompt
            places_text = ""
            for i, p in enumerate(places):
                places_text += f"\n{i+1}. {p['name']}"
                if p.get('address'):
                    places_text += f" | {p['address']}"
                if p.get('types'):
                    places_text += f" | Tipos: {', '.join(p['types'][:3])}"
                if p.get('rating'):
                    places_text += f" | Rating: {p['rating']} ({p.get('totalRatings', 0)} avaliacoes)"
                if p.get('website'):
                    places_text += f" | Website: {p['website']}"

            prompt = f"""Voce e um especialista em qualificacao de leads B2B.

A oferta do usuario e: "{offer}"

Abaixo estao negocios encontrados no Google Places. Para CADA negocio, avalie de 0 a 100 o quao provavel e que este negocio seja um bom cliente para a oferta acima. Considere:
- Relevancia do tipo de negocio para a oferta
- Se o negocio provavelmente precisa do servico/produto oferecido
- Rating e numero de avaliacoes (negocios ativos sao melhores leads)
- Se tem website (indica maturidade digital)

Negocios encontrados:
{places_text}

Responda APENAS com um JSON array. Cada item deve ter:
- "index": numero do negocio (comecando em 0)
- "score": pontuacao de 0 a 100
- "reason": motivo curto em portugues (max 15 palavras)

Exemplo de resposta:
[{{"index": 0, "score": 85, "reason": "Restaurante ativo com boa presenca online, precisa de marketing digital"}}]

Responda SOMENTE o JSON array, sem markdown, sem explicacao."""

            req_body = json.dumps({
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Voce responde apenas em JSON valido. Sem markdown, sem explicacao."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 4000
            })

            req = urllib.request.Request(
                'https://api.openai.com/v1/chat/completions',
                data=req_body.encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {api_key}'
                }
            )

            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())

            content = result['choices'][0]['message']['content'].strip()

            # Clean markdown if present
            if content.startswith('```'):
                content = content.split('\n', 1)[1] if '\n' in content else content[3:]
                if content.endswith('```'):
                    content = content[:-3]
                content = content.strip()

            scores = json.loads(content)

            # Merge scores with places data
            leads = []
            score_map = {s['index']: s for s in scores}

            for i, place in enumerate(places):
                score_info = score_map.get(i, {'score': 50, 'reason': 'Sem avaliacao'})
                lead = {
                    'name': place.get('name', ''),
                    'address': place.get('address', ''),
                    'phone': place.get('phone', ''),
                    'rating': place.get('rating', 0),
                    'totalRatings': place.get('totalRatings', 0),
                    'website': place.get('website', ''),
                    'maps_url': place.get('maps_url', ''),
                    'types': place.get('types', []),
                    'score': score_info.get('score', 50),
                    'reason': score_info.get('reason', ''),
                }
                leads.append(lead)

            # Sort by score descending
            leads.sort(key=lambda x: x['score'], reverse=True)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'leads': leads}).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

