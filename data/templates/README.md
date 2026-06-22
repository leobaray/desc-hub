# Templates de família

Cada `.yaml` desta pasta é uma **família de produto**: como classificar um item
(gatilhos), qual NCM sugerir e como redigir a descrição DUIMP. Quem consome é
`src/descricao.py` (`carregar_templates` / `escolher_template` / `compor`).

## Schema (nesta ordem)

```yaml
# Família: <nome> — comentário livre com decisões e armadilhas conhecidas.
tipo: slug_da_familia            # id; vai pro campo `template` do produto
nome: Nome em PT                 # mostrado pro LLM no prompt
prioridade: 20                   # maior testa primeiro; ausente = 0 (último)
ncm_sugerida: "87089300"         # 8 dígitos SEM pontos (padrão contabilidade/
                                 # Siscomex), entre aspas; vira seed do campo ncm

gatilhos:                        # lista; basta UM casar
  - termo solto                  #   substring (lowercase) em: código + descrição
                                 #   do invoice + atributos da spec
  - "cod:RCP"                    #   prefixo do CÓDIGO (ancorado — sem
                                 #   falso-positivo no texto)

denominacao: "Termo {codigo} para transmissão automática"   # fallback sem IA

detalhamento_instrucoes: >       # instruções pro LLM montar a descrição única
  Monte assim: "...". Não inclua número OE...
```

Só esses campos são lidos pelo código — qualquer outra chave é ignorada.

## Regras de casamento

- Templates são testados em ordem de `prioridade` decrescente; o primeiro
  gatilho que casa decide. Empate de prioridade: ordem alfabética do arquivo.
- Gatilho curto/genérico rouba item de outra família (ex.: "ring", "stm" soltos
  já causaram roubo — ver comentários em `anel_vedacao` e `jogo_discos_aco`).
  Prefira termos específicos ou `cod:PREFIXO`.

## Exceções deterministas

`disco_friccao` e `disco_friccao_trans` NÃO usam LLM: a descrição é montada em
`src/descricao.py` (`_montar_disco` / `_montar_disco_trans`). Nesses dois, só
importam `tipo`, `prioridade`, `ncm_sugerida` e `gatilhos`.

## Convenções da descrição

- UMA frase/parágrafo técnico em PT-BR; sem número OE, sem nome comercial em
  inglês, sem faixa de anos (salvo se a estrutura pedir).
- Junta/material/medida só quando vier do site/catálogo — nunca inventado.
- Famílias com disco de fricção encerram com a frase-padrão de material
  (celulose/fibras de carbono/resinas/pós metálicos).
