from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.parse

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)

        query = data.get('query', '')
        city = data.get('city', '')
        radius = data.get('radius', 10000)
        max_results = data.get('maxResults', 20)

        api_key = os.environ.get('GOOGLE_PLACES_API_KEY', '')
        if not api_key:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'GOOGLE_PLACES_API_KEY not configured'}).encode())
            return

        try:
            # First, geocode the city to get coordinates
            geocode_url = 'https://maps.googleapis.com/maps/api/geocode/json?' + urllib.parse.urlencode({
                'address': city,
                'key': api_key
            })
            geo_req = urllib.request.Request(geocode_url)
            with urllib.request.urlopen(geo_req) as geo_resp:
                geo_data = json.loads(geo_resp.read())

            if geo_data['status'] != 'OK' or not geo_data['results']:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': f'Cidade nao encontrada: {city}'}).encode())
                return

            location = geo_data['results'][0]['geometry']['location']
            lat = location['lat']
            lng = location['lng']

            # Search Google Places using Text Search
            all_results = []
            next_page_token = None

            while len(all_results) < max_results:
                params = {
                    'query': query,
                    'location': f'{lat},{lng}',
                    'radius': str(radius),
                    'key': api_key,
                    'language': 'pt-BR'
                }
                if next_page_token:
                    params['pagetoken'] = next_page_token

                search_url = 'https://maps.googleapis.com/maps/api/place/textsearch/json?' + urllib.parse.urlencode(params)
                search_req = urllib.request.Request(search_url)
                with urllib.request.urlopen(search_req) as search_resp:
                    search_data = json.loads(search_resp.read())

                if search_data['status'] not in ('OK', 'ZERO_RESULTS'):
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': f'Google Places error: {search_data["status"]}'}).encode())
                    return

                results = search_data.get('results', [])
                if not results:
                    break

                for place in results:
                    if len(all_results) >= max_results:
                        break

                    place_id = place.get('place_id', '')

                    # Get place details for phone and website
                    detail = {}
                    if place_id:
                        detail_url = 'https://maps.googleapis.com/maps/api/place/details/json?' + urllib.parse.urlencode({
                            'place_id': place_id,
                            'fields': 'formatted_phone_number,website,url',
                            'key': api_key,
                            'language': 'pt-BR'
                        })
                        detail_req = urllib.request.Request(detail_url)
                        try:
                            with urllib.request.urlopen(detail_req) as detail_resp:
                                detail_data = json.loads(detail_resp.read())
                                detail = detail_data.get('result', {})
                        except:
                            pass

                    all_results.append({
                        'name': place.get('name', ''),
                        'address': place.get('formatted_address', ''),
                        'phone': detail.get('formatted_phone_number', ''),
                        'rating': place.get('rating', 0),
                        'totalRatings': place.get('user_ratings_total', 0),
                        'website': detail.get('website', ''),
                        'maps_url': detail.get('url', ''),
                        'types': [t.replace('_', ' ') for t in place.get('types', []) if t not in ('point_of_interest', 'establishment')],
                        'place_id': place_id,
                        'lat': place.get('geometry', {}).get('location', {}).get('lat', 0),
                        'lng': place.get('geometry', {}).get('location', {}).get('lng', 0),
                        'business_status': place.get('business_status', ''),
                    })

                next_page_token = search_data.get('next_page_token')
                if not next_page_token:
                    break

                # Google requires a short delay before using next_page_token
                import time
                time.sleep(2)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'results': all_results, 'total': len(all_results)}).encode())

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

