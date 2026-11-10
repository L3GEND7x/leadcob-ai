"""Gerador de abordagens (Etapa 2).

Monta e-mail, WhatsApp, roteiro de ligação e 7 follow-ups a partir dos FATOS da ficha (nome, local,
sinal captado com fonte e data) e de HIPÓTESES de setor declaradas como tal. Regras:
  - nunca afirma que a empresa tem inadimplência ou clientes inadimplentes;
  - nada é enviado pelo sistema: o texto é copiado e enviado por uma pessoa;
  - todo texto traz saída para quem não quer mais contato (opt-out);
  - campos que o usuário não informou viram [PREENCHER].
"""
from __future__ import annotations

FILL = "[PREENCHER]"


def _signature(settings: dict) -> str:
    nome = settings.get("remetente_nome") or f"{FILL}: seu nome"
    empresa = settings.get("remetente_empresa") or f"{FILL}: sua empresa"
    contato = settings.get("remetente_contato") or f"{FILL}: telefone ou e-mail"
    return f"{nome}\n{empresa}\n{contato}"


def _best_signal(sheet: dict) -> dict | None:
    sigs = [s for s in sheet.get("signals_detail", []) if s.get("status") != "discarded"]
    return max(sigs, key=lambda s: (s.get("strength") or 0, s.get("captured_at") or "")) if sigs else None


def build(sheet: dict, settings: dict) -> dict:
    name = sheet.get("trade_name") or sheet["name"]
    servico = settings.get("servico") or "cobrança e recuperação de crédito"
    setor = sheet.get("profile_label")
    debt = [d.lower() for d in sheet.get("debt_types", [])][:2]
    best = _best_signal(sheet)
    sig = _signature(settings)
    first_name = (settings.get("remetente_nome") or FILL).split(" ")[0]
    baseado = [f"Empresa: {sheet['name']}" + (f" — {sheet.get('city')}/{sheet.get('state')}" if sheet.get("state") else "")]
    cuidados = ["Não afirme que a empresa tem inadimplência ou clientes inadimplentes: nenhuma fonte usada aqui comprova isso.",
                "O sistema não envia nada. Revise, ajuste e envie você mesma; depois registre o contato na ficha.",
                "Use apenas canais institucionais (site, e-mail ou telefone da empresa), nunca contatos pessoais."]

    if best and best["type"] == "public_procurement":
        baseado.append(f"Edital: {best['title']} ({best['source']}, captado em {(best.get('captured_at') or '')[:10]})")
        return {
            "modo": "edital",
            "aviso": "Em licitação ou credenciamento público, a comunicação segue as regras do edital. Não envie abordagem comercial "
                     "ao órgão: use os canais oficiais de esclarecimento e a proposta formal.",
            "checklist": ["Baixar e ler o edital completo e os anexos" + (f": {best['url']}" if best.get("url") else ""),
                          "Conferir requisitos de habilitação (jurídica, fiscal, técnica e econômico-financeira)",
                          "Conferir forma de remuneração, prazos e critérios de julgamento ou credenciamento",
                          "Anotar prazo de propostas e de pedidos de esclarecimento na próxima atividade da ficha",
                          "Se houver dúvida, enviar pedido de esclarecimento pelo canal indicado no edital"],
            "baseado_em": baseado, "cuidados": cuidados, "mensagens": [], "follow_ups": [],
        }

    if best and best["type"] == "hiring":
        baseado.append(f"Vaga: {best['title']} ({best['source']}, captada em {(best.get('captured_at') or '')[:10]})")
        gancho = (f"Vi que vocês publicaram a vaga \"{best['title']}\". Imagino que a área de crédito e cobrança esteja "
                  "em estruturação ou crescimento.")
        gancho_curto = f"vi a vaga \"{best['title']}\" de vocês"
    else:
        gancho = (f"Trabalho com empresas de {setor.lower()} e gostaria de me apresentar." if setor
                  else "Gostaria de me apresentar e entender se faz sentido conversarmos.")
        gancho_curto = f"trabalho com empresas de {setor.lower()}" if setor else "gostaria de me apresentar"
    if setor:
        baseado.append(f"Setor (CNAE): {setor}")
    hipotese = (f"Em empresas de {setor.lower()}, recebíveis como {' e '.join(debt)} costumam exigir acompanhamento constante."
                if setor and debt else None)
    if hipotese:
        baseado.append(f"Hipótese de setor (não é fato sobre a empresa): {hipotese}")
    optout = "Se preferirem não receber novos contatos, basta responder a esta mensagem que retiro vocês da minha lista."

    email = {
        "canal": "E-mail", "assunto": f"{servico[:1].upper() + servico[1:]} para a área financeira — {name}",
        "texto": "\n\n".join(p for p in [
            f"Olá, equipe {name},",
            gancho,
            f"Sou {settings.get('remetente_nome') or FILL}, da {settings.get('remetente_empresa') or FILL}, e trabalhamos com {servico.lower()}."
            + (f" {hipotese}" if hipotese else ""),
            "Gostaria de entender como vocês organizam hoje o acompanhamento das contas a receber e, se fizer sentido, "
            "apresentar em uma conversa de 20 minutos como poderíamos apoiar.",
            "Qual seria a melhor pessoa ou o melhor horário para isso?",
            f"Atenciosamente,\n{sig}",
            optout,
        ] if p),
    }
    whatsapp = {
        "canal": "WhatsApp (número institucional)",
        "texto": f"Olá! Aqui é {first_name}, da {settings.get('remetente_empresa') or FILL}. {gancho_curto[:1].upper() + gancho_curto[1:]} "
                 f"e trabalho com {servico.lower()}. Posso enviar uma apresentação curta por aqui ou por e-mail? "
                 "Se preferir não receber mensagens, é só avisar.",
    }
    ligacao = {
        "canal": "Roteiro de ligação",
        "etapas": [
            {"etapa": "Abertura", "texto": f"Bom dia, aqui é {first_name}, da {settings.get('remetente_empresa') or FILL}. "
                                           "Poderia falar com a pessoa responsável pelo financeiro ou pelo contas a receber?"},
            {"etapa": "Permissão", "texto": "Tem dois minutos agora ou prefere que eu ligue em outro horário?"},
            {"etapa": "Motivo", "texto": gancho + f" Trabalhamos com {servico.lower()}."},
            {"etapa": "Descoberta", "texto": "Como vocês acompanham hoje os pagamentos em atraso? Isso é feito por equipe própria, "
                                             "por um parceiro ou pelos dois? O que mais toma tempo nesse processo?"},
            {"etapa": "Próximo passo", "texto": "Faz sentido marcarmos 20 minutos para eu entender melhor e mostrar como trabalhamos?"},
            {"etapa": "Encerramento", "texto": "Agradeço pelo tempo. Vou registrar o que conversamos e envio o resumo por e-mail."},
        ],
        "objecoes": [
            {"objecao": "Já temos equipe própria.", "resposta": "Ótimo. Muitas empresas usam parceiro só para algumas faixas de atraso, "
                                                                 "liberando a equipe para o restante. Posso mostrar como funcionaria?"},
            {"objecao": "Já temos assessoria.", "resposta": "Entendo. Se um dia quiserem comparar resultados ou ter um segundo parceiro, "
                                                            "posso deixar meu contato?"},
            {"objecao": "Não temos problema com atraso.", "resposta": "Que bom. Então o tema talvez seja prevenção: posso compartilhar "
                                                                       "como estruturamos lembretes antes do vencimento?"},
            {"objecao": "Manda por e-mail.", "resposta": "Claro. Para quem envio e qual o melhor assunto para não se perder?"},
        ],
    }
    follow = [
        ("Sem resposta — 1º lembrete", 3, f"Olá, equipe {name}. Retomo meu contato sobre {servico.lower()}. Faz sentido conversarmos esta semana?"),
        ("Sem resposta — novo ângulo", 7, "Olá! Um ponto que costuma ajudar é separar o acompanhamento por faixa de atraso. "
                                          "Se for útil, envio um resumo de como fazemos. Posso enviar?"),
        ("Após reunião", 1, "Agradeço pela conversa. Resumo: [PREENCHER pontos discutidos]. Próximo passo combinado: [PREENCHER]."),
        ("Após proposta", 5, "Olá! Conseguiram avaliar a proposta enviada? Fico à disposição para ajustar o que for necessário."),
        ("Agora não — retomar depois", 90, f"Olá, equipe {name}. Combinamos de retomar o assunto: o momento agora faz mais sentido?"),
        ("Reativação de oportunidade perdida", 180, f"Olá! Conversamos há alguns meses sobre {servico.lower()}. "
                                                     "Se algo mudou na área financeira, fico à disposição."),
        ("Encerramento cordial", 14, "Como não tive retorno, encerro por aqui para não incomodar. Se precisarem no futuro, "
                                     "meu contato continua o mesmo. Agradeço a atenção!"),
    ]
    return {
        "modo": "comercial", "aviso": None, "checklist": [],
        "mensagens": [email, whatsapp, ligacao],
        "follow_ups": [{"tipo": t, "dias_depois": d, "texto": x + "\n\n" + optout} for t, d, x in follow],
        "baseado_em": baseado, "cuidados": cuidados,
    }
