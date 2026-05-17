import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 8574

books_db = {}
next_id = 1
VALID_GENRES = ["SCI_FI", "NOVEL", "HISTORY", "MANGA", "ROMANCE", "PROFESSIONAL"]


class BookServerHandler(BaseHTTPRequestHandler):

    def send_error_response(self, code, message):
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = {"errorMessage": message}
        self.wfile.write(json.dumps(response).encode())

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)

        if path == '/books/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"OK")
            return

        elif path == '/books':
            self.handle_get_books(query_params)

        elif path == '/books/total':
            self.handle_get_books(query_params, count_only=True)

        elif path == '/book':
            self.handle_get_single_book(query_params)

    def handle_get_books(self, query_params, count_only=False):
        results = list(books_db.values())

        # 1. Filter by Author (Exact match, case-insensitive)
        author_filter = query_params.get('author', [None])[0]
        if author_filter:
            results = [b for b in results if b['author'].lower() == author_filter.lower()]

        # 2. Filter by Price Range
        price_bigger_than = query_params.get('price-bigger-than', [None])[0]
        price_less_than = query_params.get('price-less-than', [None])[0]
        try:
            if price_bigger_than is not None:
                results = [b for b in results if b['price'] >= float(price_bigger_than)]
            if price_less_than is not None:
                results = [b for b in results if b['price'] <= float(price_less_than)]
        except ValueError:
            self.send_error_response(400, "Error: numeric query parameters must be numbers")
            return

        # 3. Filter by Year Range
        year_bigger_than = query_params.get('year-bigger-than', [None])[0]
        year_less_than = query_params.get('year-less-than', [None])[0]
        try:
            if year_bigger_than is not None:
                results = [b for b in results if b['year'] >= int(year_bigger_than)]
            if year_less_than is not None:
                results = [b for b in results if b['year'] <= int(year_less_than)]
        except ValueError:
            self.send_error_response(400, "Error: numeric query parameters must be numbers")
            return

        # 4. Filter by Genres (CSV String -> OR Logic)
        genres_filter = query_params.get('genres', [None])[0]
        if genres_filter:
            requested_genres = [g.strip() for g in genres_filter.split(',')]

            for g in requested_genres:
                if g not in VALID_GENRES:
                    self.send_error_response(400, f"Error: Invalid genre '{g}'")
                    return

            filtered_results = []
            for b in results:
                book_genres = [g.upper() for g in b['genres']]
                # Book must have AT LEAST ONE of the requested genres
                if any(req_g.upper() in book_genres for req_g in requested_genres):
                    filtered_results.append(b)
            results = filtered_results

        # If it's the /books/total endpoint, return count instead of the list
        if count_only:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"result": len(results)}).encode())
            return

        # 5. Sort by Title (Ascending, Case-Insensitive)
        sorted_results = sorted(results, key=lambda x: x['title'].lower())

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"result": sorted_results}).encode())

    def handle_get_single_book(self, query_params):
        id_param = query_params.get('id', [None])[0]
        if id_param is None:
            self.send_error_response(400, "Error: id parameter is missing")
            return

        try:
            book_id = int(id_param)
        except ValueError:
            self.send_error_response(400, "Error: id must be a number")
            return

        if book_id in books_db:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"result": books_db[book_id]}).encode())
        else:
            # Note the capital 'B' in Book, as required by the automation
            self.send_error_response(404, f"Error: no such Book with id {book_id}")

    def do_POST(self):
        global next_id
        parsed_url = urlparse(self.path)

        if parsed_url.path == '/book':
            connect_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(connect_length)
            book_data = json.loads(post_data.decode('utf-8'))

            incoming_title_lower = book_data['title'].lower()
            for existing_book in books_db.values():
                if existing_book['title'].lower() == incoming_title_lower:
                    self.send_error_response(409,
                                             f"Error: Book with the title [{book_data['title']}] already exists in the system")
                    return

            if not (1940 <= book_data['year'] <= 2100):
                self.send_error_response(409,
                                         f"Error: Can't create new Book that its year [{book_data['year']}] is not in the accepted range [1940 -> 2100]")
                return

            if book_data['price'] <= 0:
                self.send_error_response(409, "Error: Can't create new Book with negative price")
                return

            new_id = next_id
            book_data['id'] = new_id
            books_db[new_id] = book_data
            next_id += 1

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"result": new_id}).encode())

    def do_PUT(self):
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)

        if parsed_url.path == '/book':
            id_param = query_params.get('id', [None])[0]
            price_param = query_params.get('price', [None])[0]

            if id_param is None:
                self.send_error_response(400, "Error: id parameter is missing")
                return

            try:
                book_id = int(id_param)
            except ValueError:
                self.send_error_response(400, "Error: id must be a number")
                return

            if book_id not in books_db:
                self.send_error_response(404, f"Error: no such Book with id {book_id}")
                return

            # Check if price was passed in query, fallback to checking the JSON body if needed
            new_price = None
            if price_param is not None:
                try:
                    new_price = float(price_param)
                except ValueError:
                    self.send_error_response(400, "Error: price must be a number")
                    return
            else:
                try:
                    connect_length = int(self.headers.get('Content-Length', 0))
                    if connect_length > 0:
                        put_data = self.rfile.read(connect_length)
                        body_data = json.loads(put_data.decode('utf-8'))
                        new_price = float(body_data['price'])
                except (json.JSONDecodeError, KeyError, ValueError):
                    self.send_error_response(400, "Error: price parameter is missing or invalid")
                    return

            if new_price is None or new_price <= 0:
                self.send_error_response(409, "Error: price must be positive")
                return

            books_db[book_id]['price'] = new_price

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"result": "OK"}).encode())

    def do_DELETE(self):
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)

        if parsed_url.path == '/book':
            id_param = query_params.get('id', [None])[0]
            if id_param is None:
                self.send_error_response(400, "Error: id parameter is missing")
                return

            try:
                book_id = int(id_param)
            except ValueError:
                self.send_error_response(400, "Error: id must be a number")
                return

            if book_id not in books_db:
                self.send_error_response(404, f"Error: no such Book with id {book_id}")
                return

            del books_db[book_id]

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"result": "OK"}).encode())


def run_server():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, BookServerHandler)
    print(f"Starting server on port {PORT}...")
    httpd.serve_forever()


if __name__ == '__main__':
    run_server()