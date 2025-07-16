A pasta `extensions` tem uma finalidade específica e importante na arquitetura do projeto:

### Finalidade da Pasta `extensions`:
1. **Gerenciamento de Integrações com Serviços Externos**  
   Centraliza os clients/adapters para comunicação com APIs de terceiros (Bitrix24, Digisac, Conta Azul).

2. **Configuração de Instâncias Reutilizáveis**  
   Mantém objetos singleton que encapsulam conexões e estados persistentes com serviços externos.

3. **Abstração de Complexidade**  
   Isola detalhes de implementação específicos de cada plataforma integrada.

### Exemplos de Conteúdo:

#### `extensions/digisac.py`
```python
import requests
from flask import current_app

class DigisacClient:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        })
    
    def send_message(self, contact_id, text):
        endpoint = f"{self.base_url}/messages"
        payload = {
            "contactId": contact_id,
            "text": text,
            "ticketDepartmentId": current_app.config['DIGISAC_DEPT_ID']
        }
        response = self.session.post(endpoint, json=payload)
        response.raise_for_status()
        return response.json()
    
    def upload_file(self, contact_id, file_bytes, filename):
        # Implementação de upload de arquivos
        ...
```

#### `extensions/conta_azul.py`
```python
class ContaAzulAuth:
    def __init__(self):
        self.tokens = {}
        
    def refresh_tokens(self):
        # Lógica de refresh OAuth
        ...
    
    def get_valid_token(self):
        if self._tokens_expired():
            self.refresh_tokens()
        return self.tokens['access_token']
```

### Por que separar em `extensions` e não em `services`?

| Critério          | `extensions`                          | `services`                          |
|-------------------|---------------------------------------|-------------------------------------|
| **Responsabilidade** | Conexões técnicas com externos        | Lógica de negócio                   |
| **Estado**        | Mantém estado (tokens, sessões)       | Stateless (puro processamento)      |
| **Complexidade**  | Lógica low-level de integração        | Regras de negócio/dados             |
| **Reuso**         | Alto (múltiplos serviços usam)        | Específico por domínio              |

### Fluxo de Uso Típico:
```mermaid
graph LR
    A[Routes] --> B[Services]
    B --> C[Extensions]
    C --> D[APIs Externas]
```

**Exemplo prático em uma rota**:
```python
# routes/webhooks.py
from extensions import digisac

@bp.route('/certificate-alert', methods=['POST'])
def handle_alert():
    # 1. Valida payload
    data = request.get_json()
    
    # 2. Usa service para lógica de negócio
    renewal = RenewalService.create(data)
    
    # 3. Usa extension para comunicação técnica
    digisac.send_message(
        contact_id=renewal.contact_id,
        text=f"Seu certificado expira em {renewal.days_left} dias"
    )
```

### Benefícios Chave:
1. **Separação de Preocupações Clara**  
   Isola detalhes técnicos de integração da lógica de negócio

2. **Evita Duplicação**  
   Conexões e autenticações são compartilhadas globalmente

3. **Facilita Testes**  
   Permite mockar facilmente toda a camada externa

4. **Gerência Centralizada**  
   Configurações de timeout/retry em um único lugar

5. **Vida Útil Controlada**  
   Gerencia ciclo de vida de tokens e sessões

Esta abordagem segue o padrão **Adapter Pattern** e **Dependency Inversion**, criando uma camada anti-corrupção entre seu núcleo de aplicação e serviços externos.