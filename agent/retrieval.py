"""Small local semantic index. Embeddings from Ollama; no hosted/vector DB dependency."""
import hashlib
import json
import math
import os
import threading
import urllib.request
from pathlib import Path

class RunbookRetriever:
    def __init__(self, directory, embed=None, model=None):
        self.directory = Path(directory)
        self.model = model or os.environ.get('EMBEDDING_MODEL', 'qwen3-embedding:0.6b')
        self.embed = embed or self._embed
        self._fingerprint = None
        self._documents = []
        self._vectors = []
        self._lock = threading.Lock()

    def _embed(self, texts):
        endpoint = os.environ.get('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')
        request = urllib.request.Request(endpoint + '/api/embed',
            data=json.dumps({'model':self.model, 'input':texts, 'truncate':False}).encode(),
            headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=45) as response:
            vectors = json.load(response)['embeddings']
        if len(vectors) != len(texts) or not all(vectors):
            raise ValueError('Invalid embedding response')
        return vectors

    @staticmethod
    def cosine(a, b):
        if len(a) != len(b):
            raise ValueError('Embedding dimensions differ')
        denom = math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
        return sum(x*y for x,y in zip(a,b))/denom if denom else 0.0

    def search(self, query, top_k=3):
        if not query.strip():
            return {'status':'no_match','reason':'empty_query','candidates':[]}
        documents = [{'id':p.stem,'text':p.read_text()} for p in sorted(self.directory.glob('*.md'))]
        if not documents:
            return {'status':'no_match','reason':'empty_corpus','candidates':[]}
        fingerprint = hashlib.sha256((self.model+json.dumps(documents,ensure_ascii=False)).encode()).hexdigest()
        with self._lock:
            if self._fingerprint != fingerprint:
                vectors = self.embed([d['text'] for d in documents])
                self._documents,self._vectors,self._fingerprint = documents,vectors,fingerprint
            vector = self.embed(['Instruct: Retrieve the operational incident runbook relevant to this symptom.\nQuery: '+query])[0]
            ranked = sorted([{**d, 'score':self.cosine(vector,v)} for d,v in zip(self._documents,self._vectors)],key=lambda d:d['score'],reverse=True)
        candidates = [{'id':d['id'],'score':round(d['score'],4),'title':d['text'].splitlines()[0].lstrip('# ')} for d in ranked[:top_k]]
        # Design defaults, not calibrated probabilities. Keep ambiguous matches visible.
        minimum = float(os.environ.get('RETRIEVAL_MIN_SCORE','0.45'))
        margin = float(os.environ.get('RETRIEVAL_MIN_MARGIN','0.025'))
        gap = ranked[0]['score']-ranked[1]['score'] if len(ranked)>1 else 1
        accepted = ranked[0]['score'] >= minimum and gap >= margin
        return {'status':'matched' if accepted else 'no_match', 'reason':'accepted' if accepted else 'low_score_or_ambiguous',
                'model':self.model,'index_hash':fingerprint,'min_score':minimum,'min_margin':margin,
                'candidates':candidates, 'selected':ranked[0]['id'] if accepted else None,
                'text':ranked[0]['text'] if accepted else None}
