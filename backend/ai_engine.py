"""
AI Engine — Claude API with knowledge base context.
Multi-tenant: all operations scoped by client_id.
"""
import re
import json
import anthropic
from database import (
    get_config, get_knowledge, save_message, upsert_lead,
    get_session_messages
)

BUILTIN_KB = """
# Techmatic Systems — Company Overview

## About Techmatic Systems
Techmatic Systems is a global IT consulting and software services company. We specialize in enterprise technology solutions that drive digital transformation, operational efficiency, and sustainable growth. Headquartered with a global delivery model, Techmatic serves clients across North America, Europe, the Middle East, and Asia.

## Core Services

### 1. Digital Transformation & Cloud Services
- Digital consulting and IT strategy
- Cloud migration (AWS, Azure, GCP)
- DevOps/SRE implementation
- Process reengineering and automation
- Infrastructure modernization

### 2. Data Analytics & Business Intelligence
- Advanced analytics and visualization
- Data warehousing (Snowflake, Redshift)
- Real-time dashboards and reporting
- Predictive analytics and ML models
- Business intelligence strategy

### 3. AI & ML Integration
- Machine learning model development
- Natural language processing (NLP)
- Computer vision solutions
- AI-powered process automation
- LLM integration and fine-tuning

### 4. ERP Solutions
**Odoo ERP:**
- Full Odoo implementation and customization
- CRM, Sales, Accounting, Inventory, HR modules
- Odoo Partner with certified consultants
- Migration from legacy ERP systems

**Acumatica ERP:**
- Cloud-based ERP for mid-market businesses
- Finance, distribution, manufacturing modules
- Implementation and ongoing support

### 5. Custom E-commerce Development
- End-to-end e-commerce platform development
- Multi-channel commerce integration
- Payment gateway integration
- Inventory and order management
- Mobile commerce solutions

### 6. Quality Engineering & Testing
- Manual and automated testing
- Performance and load testing
- Security testing
- CI/CD pipeline integration
- Test strategy and governance

### 7. Data Solutions
- Snowflake data platform implementation
- ETL/ELT pipeline development
- Data governance and compliance
- Master data management

### 8. Software Development
- Custom enterprise application development
- API development and integration
- Legacy system modernization
- Mobile app development (iOS/Android)

## Industries Served
- Retail & E-commerce
- Healthcare & Life Sciences
- Financial Services & Fintech
- Manufacturing & Supply Chain
- Logistics & Transportation
- Real Estate & Property Management
- Education & EdTech
- Hospitality & Travel

## Why Choose Techmatic?
- 10+ years of industry experience
- Global delivery model with local expertise
- Certified team across Microsoft, AWS, Odoo, Snowflake
- Agile methodology for fast, iterative delivery
- 24/7 support and dedicated account management
- 500+ successful projects delivered
- Clients in 20+ countries

## Contact
- Website: https://www.techmaticsys.com
- Contact page: https://www.techmaticsys.com/contact
- Office locations across India and global offices

## Startup Tech Partner Program
Techmatic's Startup Tech Partner program offers:
- Dedicated technology partnership for startups
- Flexible engagement models (equity, retainer, milestone-based)
- End-to-end product development support
- MVP to scale-up technology roadmap
- Mentorship and advisory services
"""


def build_context(knowledge_rows):
    if not knowledge_rows:
        return BUILTIN_KB[:6000]
    parts = []
    total = 0
    for row in knowledge_rows:
        content = row.get('content') or ''
        if not content:
            continue
        chunk = f"\n### {row.get('title', row.get('url', 'Source'))}\n{content}\n"
        if total + len(chunk) > 7000:
            break
        parts.append(chunk)
        total += len(chunk)
    return BUILTIN_KB[:2000] + "\n\n## ADDITIONAL SCRAPED CONTENT\n" + "\n".join(parts) if parts else BUILTIN_KB[:6000]


def build_system_prompt(config, knowledge_rows):
    base = config.get('system_prompt') or ''
    kb_context = build_context(knowledge_rows)
    questions = config.get('qualification_questions') or ''
    q_list = [q.strip() for q in questions.strip().split('\n') if q.strip()]
    q_fmt = '\n'.join(f'- {q}' for q in q_list)

    return f"""{base}

---
## KNOWLEDGE BASE
Use this information to answer questions accurately:

{kb_context}

---
## QUALIFICATION FLOW
{'Ask these questions naturally, one at a time: ' + chr(10) + q_fmt if config.get('lead_questions_enabled') else 'Skip qualification questions.'}

## LEAD CAPTURE
When interest is shown, ask for name and email naturally. After collecting contact info, thank them and say the team will follow up within 24 hours.
"""


async def handle_incoming_message(source, message, session_id, client_id=1):
    """
    Modular message handler — source: 'web' | 'whatsapp'
    Now scoped by client_id for multi-tenant support.
    """
    config = get_config(client_id)
    if not config or not config.get('api_key'):
        return "⚠️ The AI assistant is not configured yet. Please contact support."

    knowledge_rows = get_knowledge(client_id)
    history = get_session_messages(session_id, limit=30, client_id=client_id)

    messages = []
    for h in history:
        messages.append({
            "role": "user" if h['role'] == 'user' else "assistant",
            "content": h['content']
        })
    messages.append({"role": "user", "content": message})

    save_message(session_id, 'user', message, source, client_id)

    system_prompt = build_system_prompt(config, knowledge_rows)

    try:
        client = anthropic.Anthropic(api_key=config['api_key'])
        response = client.messages.create(
            model=config.get('model_name') or 'claude-4-6-sonnet-20260215',
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        reply = response.content[0].text
    except anthropic.AuthenticationError:
        reply = "⚠️ AI configuration error. Please contact support."
    except Exception as e:
        reply = f"⚠️ Something went wrong. Please try again."

    save_message(session_id, 'bot', reply, source, client_id)

    # Background lead extraction
    if len(history) >= 4:
        await _extract_lead(session_id, history + [
            {'role': 'user', 'content': message},
            {'role': 'bot', 'content': reply}
        ], config, client_id)

    return reply


async def _extract_lead(session_id, history, config, client_id=1):
    try:
        convo = "\n".join(
            f"{'User' if h['role'] == 'user' else 'Bot'}: {h['content']}"
            for h in history[-14:]
        )
        extract_prompt = f"""Extract lead information from this conversation. Return ONLY a JSON object:
{{
  "name": null,
  "email": null,
  "phone": null,
  "industry": null,
  "business_type": null,
  "problem": null,
  "timeline": null,
  "service_interest": null
}}
Conversation:
{convo}"""

        client = anthropic.Anthropic(api_key=config['api_key'])
        resp = client.messages.create(
            model='claude-4-6-haiku-20260307',
            max_tokens=300,
            messages=[{"role": "user", "content": extract_prompt}]
        )
        raw = resp.content[0].text.strip()
        m = re.search(r'\{.*\}', raw, re.S)
        if m:
            data = json.loads(m.group())
            lead = {k: v for k, v in data.items()
                    if v and str(v).lower() not in ('null', 'none', '', 'unknown')}
            if lead.get('email') or lead.get('phone'):
                lead['source'] = 'web'
                upsert_lead(session_id, client_id, **lead)
    except Exception:
        pass
