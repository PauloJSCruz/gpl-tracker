# ⛽ GPL Tracker - Contador Financeiro Inteligente & ROI de Conversão para GPL

Aplicação Python para acompanhar o retorno financeiro do investimento na conversão de um automóvel a gasolina para GPL (Gás de Petróleo Liquefeito), concebida para responder de forma simples, transparente e sem atrito a:

* **Quanto dinheiro já poupei com GPL?**
* **Quanto já recuperei do custo da conversão?**
* **Quanto falta recuperar?**
* **Quantos km faltam aproximadamente para o Break-Even?**
* **Quanto tempo falta aproximadamente?**
* **Já recuperei o investimento?**

O foco é a **mínima interação**: depois de selecionar o posto (com postos habituais e favoritos no topo), o utilizador só precisa de introduzir os **Km percorridos** e o **Valor pago (€)**. Todo o resto é obtido via APIs oficiais ou calculado automaticamente.

---

## 🚀 Como Iniciar

### 1. Instalação de Dependências
### Opção A: Executar via Docker no Servidor (Recomendado)

O projeto inclui configuração pronta para Docker com persistência total dos dados na pasta local `./data`.

#### Com Docker Compose:
```bash
docker compose up -d --build
```
A aplicação fica disponível em `http://<ip-do-servidor>:8000`.

#### Com Docker CLI:
```bash
# 1. Construir a imagem
docker build -t gpl-tracker .

# 2. Executar com volume para persistência da base de dados SQLite
docker run -d \
  --name gpl-tracker \
  --restart unless-stopped \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  gpl-tracker
```

> **Persistência de Dados**: O ficheiro da base de dados SQLite é guardado em `./data/gpl_tracker.db` na máquina anfitriã. Mesmo que o contentor seja reiniciado, atualizado ou reconstruído, todos os abastecimentos, postos favoritos e configurações são preservados intactos.

---

### Opção B: Executar Localmente com Python

1. **Instalação de Dependências:**
```bash
pip install -r requirements.txt
```

### 2. Executar a Aplicação
2. **Executar a Aplicação:**
```bash
python app.py
```
A aplicação iniciará o servidor local e abrirá automaticamente o navegador em `http://127.0.0.1:8000`.

---

## 📐 Fórmulas Utilizadas

A aplicação utiliza de forma consistente as seguintes fórmulas financeiras exatas:

### 1. Litros de GPL
$$\text{litros\_gpl} = \frac{\text{valor\_pago}}{\text{preco\_gpl}}$$

### 2. Consumo GPL (L/100 km)
$$\text{consumo\_gpl} = \frac{\text{litros\_gpl}}{\text{km\_percorridos}} \times 100$$

### 3. Consumo Equivalente de Gasolina (L/100 km)
Tendo em conta o aumento percentual de consumo em GPL ($\text{aumento\_gpl} = 20\%$ por defeito):
$$\text{consumo\_gasolina} = \frac{\text{consumo\_gpl}}{1 + \frac{\text{aumento\_gpl}}{100}}$$

*Exemplo:* Para um consumo GPL de $8,89\text{ L/100 km}$ e aumento de $20\%$, o consumo gasolina equivalente é:
$$\frac{8,89}{1,20} \approx 7,41\text{ L/100 km}$$

### 4. Custo Hipotético da Gasolina (€)
$$\text{custo\_gasolina} = \frac{\text{km\_percorridos}}{100} \times \text{consumo\_gasolina} \times \text{preco\_gasolina}$$

### 5. Poupança do Período (€)
$$\text{poupanca} = \text{custo\_gasolina} - \text{valor\_pago}$$

### 6. ROI e Break-Even
* **Percentagem Recuperada:**
  $$\text{percentagem\_recuperada} = \frac{\text{poupanca\_acumulada}}{\text{custo\_conversao}} \times 100$$
* **Valor em Falta:**
  $$\text{valor\_em\_falta} = \max(0,\; \text{custo\_conversao} - \text{poupanca\_acumulada})$$
* **Km Restantes:**
  $$\text{km\_restantes} = \frac{\text{valor\_em\_falta}}{\text{poupanca\_media\_km}}$$
* **Tempo Restante (Meses):** Baseado na média real de km/mês calculada a partir dos abastecimentos registados ao longo do tempo (intervalo temporal $\ge 7$ dias e $\ge 2$ registos). Se não existirem dados suficientes, a aplicação indica explicitamente *"Dados insuficientes para estimar o break-even"* em vez de inventar projeções.

---

## 🔌 Camada de Fornecedores (Providers) e Resiliência Offline

A aplicação implementa a estratégia de fornecedores em cascata sem bloqueios:

```
DGEG REST API (precoscombustiveis.dgeg.gov.pt)
       ↓ (se falhar ou exceder timeout de 4s)
Cache Local SQLite (preço guardado daquele posto)
       ↓ (se não existir na cache daquele posto)
Último Preço Conhecido (histórico de abastecimentos anteriores)
       ↓ (se não existir histórico)
API Aberta (apiaberta.pt - médias nacionais de referência)
       ↓ (se offline e sem histórico)
Entrada Manual
```

Cada preço indica claramente a sua proveniência:
* `DGEG` (Oficial com data de atualização)
* `Cache` (Com data do registo anterior)
* `Média Nacional` (API Aberta)
* `Manual`

---

## 🧪 Testes Automatizados

Para executar a suite completa de testes:
```bash
python -m pytest
```

A suite cobre:
1. Cenário de validação exato do utilizador (450 km, 0.85 €/L GPL, 1.75 €/L Gasolina, 34 € pagos, 20% aumento).
2. Validação da fórmula do consumo gasolina equivalente.
3. Testes de acumulação, ROI, estado de recuperação e break-even com dados insuficientes.
4. Testes de fallback offline e parsing de strings de preço da DGEG.
5. Testes de persistência SQLite, favoritos, histórico e duplicação.
6. Testes de exportação para CSV e Excel (.xlsx).

---

## 🗂 Estrutura do Projeto

```
GPL/
├── Dockerfile                     # Imagem Docker multi-stage optimizada
├── docker-compose.yml             # Orquestração com volume persistente
├── .dockerignore                  # Ficheiros excluídos do build Docker
├── app.py                         # Ponto de entrada (arranque do servidor e browser)
├── requirements.txt               # Dependências do projeto
├── README.md                      # Documentação
├── data/                          # Volume persistente da base de dados SQLite
│   └── gpl_tracker.db             # Base de dados SQLite (criada automaticamente)
├── gpl_tracker/
│   ├── config.py                  # Configurações e caminhos
│   ├── models/
│   │   ├── database.py            # SQLite e gestão de tabelas
│   │   └── schemas.py             # Schemas Pydantic
│   ├── calculations/
│   │   └── engine.py              # Fórmulas matemáticas e ROI
│   ├── providers/
│   │   ├── base.py                # Interfaces abstratas
│   │   ├── dgeg_provider.py       # API DGEG oficial
│   │   ├── apiaberta_provider.py  # API Aberta
│   │   ├── cached_provider.py     # Gestor híbrido com cache e fallback
│   │   └── receipt_parser.py      # Interface para OCR futuro
│   ├── services/
│   │   ├── vehicle_service.py     # Definições do veículo
│   │   ├── station_service.py     # Postos, favoritos e pesquisa
│   │   ├── refueling_service.py   # Registo e histórico de abastecimentos
│   │   └── export_service.py      # Exportações CSV e Excel
│   └── web/
│       ├── api.py                 # Rotas FastAPI
│       └── static/
│           ├── index.html         # Dashboard SPA
│           ├── app.js             # Lógica e cálculos em tempo real
│           └── style.css          # Estilos modernos
└── tests/
    ├── test_engine.py             # Testes das fórmulas e ROI
    ├── test_providers.py          # Testes de providers e fallback
    ├── test_services.py           # Testes de serviços e histórico
    └── test_export.py             # Testes de exportação
```

