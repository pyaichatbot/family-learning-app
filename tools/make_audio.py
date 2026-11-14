#!/usr/bin/env python3
"""Make the recorded clips in audio/ with the macOS voices.

1. Start a static server in the project folder and open  http://localhost:8765/?audiolist=1
   in a browser while this script runs with --collect: the page posts the list of
   sentences to it, saved as audio/list.json.
2. Run without arguments: every entry in audio/list.json becomes audio/<lang>-<hash>.mp3
   and audio/index.json lists what exists. Delete the mp3 files to record them again.
Needs macOS `say` and `ffmpeg`.
"""
import json, os, struct, subprocess, sys, tempfile, re
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'audio')
VOICE = {'de': 'Anna', 'en': 'Daniel'}
TEMPO = '0.88'  # speed of normal clips: a little slower than the voice's default, for children
SLOW = '0.6'    # letters and sound pairs, for a five-year-old


def norm(x):
    return re.sub(r'^[\s.!?,…]+|[\s.!?,…]+$', '', x)


def ahash(x):  # must match ahash() in index.html (FNV-1a over UTF-16 units)
    h = 2166136261
    b = x.encode('utf-16-le')
    for i in range(0, len(b), 2):
        h ^= struct.unpack('<H', b[i:i + 2])[0]
        h = (h * 16777619) & 0xffffffff
    return '%08x' % h


def collect():
    class H(BaseHTTPRequestHandler):
        def _cors(self):
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Headers', 'content-type')

        def do_OPTIONS(self):
            self.send_response(204); self._cors(); self.end_headers()

        def do_POST(self):
            body = self.rfile.read(int(self.headers['content-length']))
            items = json.loads(body)
            with open(os.path.join(ROOT, 'list.json'), 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False, indent=0)
            self.send_response(200); self._cors(); self.end_headers()
            print('saved', len(items), 'entries'); sys.stdout.flush()
            os._exit(0)

        def log_message(self, *a):
            pass
    HTTPServer(('127.0.0.1', 8766), H).serve_forever()


def build():
    items = json.load(open(os.path.join(ROOT, 'list.json'), encoding='utf-8'))
    ids, made, todo = [], 0, {}
    for it in items:  # [lang, text] or [lang, text, 1] for a slow recording; slow wins when a text appears twice
        lang, text, slow = it[0], it[1], len(it) > 2
        key = norm(text)
        if key:
            cid = lang + '-' + ahash(lang + '|' + key)
            todo[cid] = (lang, text, slow or todo.get(cid, (0, 0, False))[2])
    def one(cid):
        lang, text, slow = todo[cid]
        out = os.path.join(ROOT, cid + '.mp3')
        if os.path.exists(out):
            return 0
        spoken = ' [[slnc 320]] '.join(text.split()) if slow else text  # a short pause between the words of slow clips
        with tempfile.TemporaryDirectory() as d:
            aiff = os.path.join(d, 'a.aiff')
            for attempt in range(4):  # `say` sometimes hangs; give up after 20 s and try again
                try:
                    subprocess.run(['say', '-v', VOICE[lang], '-o', aiff, spoken], check=True, timeout=20)
                    break
                except subprocess.TimeoutExpired:
                    if attempt == 3:
                        raise
            # `say -r` hardly slows these voices, so stretch the sound instead (pitch stays the same)
            subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', aiff, '-filter:a', 'atempo=' + (SLOW if slow else TEMPO),
                            '-ac', '1', '-ar', '22050', '-b:a', '40k', out], check=True)
        return 1
    ids = list(todo)
    with ThreadPoolExecutor(4) as ex:
        made = sum(ex.map(one, ids))
    ids = sorted(set(ids))
    json.dump(ids, open(os.path.join(ROOT, 'index.json'), 'w'))
    print(len(ids), 'clips,', made, 'new')


if __name__ == '__main__':
    collect() if '--collect' in sys.argv else build()
