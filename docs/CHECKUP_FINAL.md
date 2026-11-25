# Check-up final da versão Flet (prompt 47, 25/11/2026)

Feito num banco LOCAL novo (SQLite, `alembic upgrade head` + seed, filial 1007), nunca em
produção. Testes automáticos: `tests/test_checkup_final.py` (37 testes, pelos serviços).
Telas: Playwright/Chromium no app local com 22 ordens, papéis admin, manutencao e usuario,
a 360, 390, 800 e 1280 px (Home no topo e no fim da lista, Perfil no topo e no fim).

Resultado: **nenhum erro encontrado nos serviços nem nas telas conferidas; nenhuma
correção feita.** Duas diferenças entre o pedido e a regra atual (entrada de horas e de
valores) são regras decididas no prompt 22 e ficam para a 2.0.

## Preparação

Usuários de teste (pedido explícito deste check-up, exceção à regra de nomes com cara de
papel), todos na filial 1007, criados pelo mesmo serviço da tela de administração
(`usuarios.criar_usuario`), cada um com a troca de senha obrigatória feita:
`usuario`, `usuario2` (papel usuario), `manutencao`, `manutencao2` (papel manutencao) e o
`admin` do seed.

### Para repetir no app publicado (tela de administração, não a CLI)

1. Entre como `admin`.
2. **Perfil** > **Usuários** > **Novo usuário**.
3. Nome `Usuário Teste 1`, Login `usuario`, Papel **Usuário**, Filial padrão **1007**,
   Filiais permitidas: só 1007. **Criar usuário**.
4. Anote a **Senha temporária** mostrada (aparece uma vez só).
5. Repita para `usuario2` (Usuário), `manutencao` e `manutencao2` (Manutenção).
6. Em cada um, o primeiro login pede a troca de senha: troque e entre.

## Parte A — papéis (papel x ação)

Exceções conferidas com o tipo exato (`ErroPermissao`, `ErroValidacao`,
`ErroAutenticacao`, `ErroTrocaDeSenhaPendente`).

| Papel | Ação | Esperado | Resultado | Evidência |
|---|---|---|---|---|
| usuario | Criar solicitação (título, descrição, urgência) | ok, filial travada | ok | `test_a_usuario_cria_solicitacao_com_filial_travada` |
| usuario | Criar solicitação em outra filial | recusa | `ErroPermissao` (ok) | idem |
| usuario, usuario2 | Ver TODAS as ordens da 1007 (de outros e da manutenção) | sim, sem custo, item, previsto, realizado, executor, prioridade, histórico | ok | `test_a_usuario_ve_todas_as_ordens_da_filial_sem_custo` |
| usuario | Ver histórico de eventos | recusa | `ErroPermissao` (ok) | idem |
| usuario2 | Editar / cancelar solicitação do usuario | recusa | `ErroPermissao` (ok) | `test_a_usuario2_nao_edita_nem_cancela_do_usuario` |
| usuario | Editar e cancelar a própria Aberta | ok | ok | `test_a_usuario_edita_e_cancela_a_propria_so_aberta` |
| usuario | Editar / cancelar a própria depois de sair de Aberta | recusa | `ErroPermissao` (ok) | idem |
| usuario | Relatório, Lixeira, usuários, SLA, especialidades, motivos, ações da manutenção | recusa | `ErroPermissao` em todas (ok) | `test_a_usuario_sem_acesso_a_areas_da_manutencao_e_admin` |
| manutencao | Ver todas as ordens com custos | ok | ok | `test_a_manutencao_ve_tudo_com_custos` |
| manutencao | Iniciar sem previsto | recusa com motivos | `ErroValidacao` citando tempo previsto, tipo, especialidade e custo/Sem gasto (ok) | `test_a_iniciar_recusado_ate_as_pendencias_com_motivos` |
| manutencao | Assumir e iniciar | prioridade = urgência; urgência igual | ok | idem |
| manutencao2 | Concluir / desfazer início de ordem iniciada por manutencao | recusa | `ErroPermissao` (ok) | `test_a_manutencao2_nao_conclui_nem_desfaz_o_inicio_de_outro` |
| manutencao | Desfazer o próprio início | ok | ok | idem |
| admin | Concluir ordem iniciada por manutencao | ok | ok | idem |
| manutencao | OS direta, Sem gasto previsto e realizado, itens (incluir, alterar, remover) | ok | ok | `test_a_os_direta_sem_gasto_e_itens` |
| manutencao | Concluir sem realizado / sem nota | recusa | `ErroValidacao` (ok) | idem |
| manutencao | Usuários, editar SLA, excluir, Lixeira, especialidades, motivos | recusa | `ErroPermissao` (ok) | `test_a_manutencao_sem_acesso_a_admin_e_sem_mudar_urgencia_ou_filial` |
| manutencao | Mudar urgência / filial | recusa | `ErroPermissao` (ok) | idem |
| admin | Escolher a filial nos dois formulários | ok | ok | `test_a_admin_filial_nos_dois_formularios` |
| manutencao | Alterar ordem concluída | recusa | `ErroPermissao` (ok) | `test_a_admin_edita_concluida_cancela_exclui_e_restaura` |
| admin | Alterar ordem concluída (inclusive realizado e itens) | ok | ok | idem |
| admin | Cancelar Aberta sem / com motivo | recusa / ok | `ErroValidacao` / ok | idem |
| admin | Excluir com motivo e restaurar | some das listas; volta com o mesmo número | ok | idem |
| admin | Usuários: criar, filiais permitidas, redefinir senha, desativar | ok | ok | `test_a_admin_usuarios_sla_especialidades_motivos` |
| redefinido | Próxima ação antes de trocar a senha | recusa | `ErroTrocaDeSenhaPendente` (ok) | idem |
| desativado | Próxima ação | recusa | `ErroAutenticacao` (ok) | idem |
| admin | SLA, especialidades, motivos de cancelamento | ok | ok | idem |

## Parte B — valores

| Verificação | Pedido no prompt 47 | Comportamento atual | Resultado | Evidência |
|---|---|---|---|---|
| Hora/duração '1', '15' | 0:01, 0:15 (dígitos pela direita) | 1:00, 15:00 (1 ou 2 dígitos = horas) | **regra diferente, fica para a 2.0** | `test_b_duracao_atual` |
| '150', '1500', '219', '1000' | 1:50, 15:00, 2:19, 10:00 | iguais | ok | idem |
| '75' | 0:75 marcado inválido | 75:00 (75 horas, aceito) | **regra diferente, fica para a 2.0** | idem |
| Minutos acima de 59 ('175' = 1:75) | inválido | 'Minutos devem ficar entre 00 e 59.' | ok | `test_b_minutos_e_hora_invalidos` |
| Hora de relógio '2400' | inválida | inválida | ok | idem |
| Backspace tira o último dígito | sim | o campo é texto livre, sem máscara ao vivo: o apagar é o do navegador | ok (sem máscara) | manual |
| Dinheiro '1', '15', '1500', '123456' | 0,01; 0,15; 15,00; 1.234,56 | R$ 1,00; 15,00; 1.500,00; 123.456,00 (dígitos = reais; centavos depois da vírgula) | **regra diferente, fica para a 2.0** | `test_b_dinheiro_atual` |
| '2,19', '10,00', '1.234,56' | 2,19; 10,00; 1.234,56 | iguais | ok | idem |
| Tamanho máximo | respeitado | R$ 99.999.999,99; acima: mensagem | ok | `test_b_dinheiro_limite` |
| 1,5 x R$ 33,33 | R$ 50,00 | R$ 50,00 | ok | `test_b_totais` |
| Nada preenchido | 'A DEFINIR' / '—', nunca R$ 0,00 | 'A DEFINIR' / '—' | ok | idem |
| Sem gasto | conta R$ 0 | 'Sem gasto' | ok | idem |
| Diferenças: acima, abaixo, igual, não previsto, sem gasto | frases sem divisão por zero | ok | ok | `test_b_diferencas` |
| Diferença de tempo | '2h58 abaixo do previsto', sem sinal de menos | ok | ok | idem |
| Data e hora em São Paulo, ordem aberta às 23:30 | 25/11/2026 23:30 | ok | ok | `test_b_datas_no_fuso_incluindo_23h30` |
| Números consecutivos, nunca reaproveitados; busca | ok | ok (formato atual `1007-2026-000001`) | ok | `test_b_numeros_consecutivos_nunca_reutilizados_e_busca` |

**Por que a entrada de horas e valores não foi mudada:** desde o prompt 22 não há
máscara ao vivo (em 4G lento a reescrita do campo perdia dígitos) e a regra decidida é
'dígitos = horas ou reais inteiros'. Passar a 'dígitos pela direita' é mudança de regra
(proibida neste prompt). **Na 2.0:** máscara no próprio navegador (sem ida e volta ao
servidor), que resolve o problema que levou à regra atual.

## Parte C — comportamento

| Verificação | Resultado | Evidência |
|---|---|---|
| Aberta -> Em execução -> Concluída; desfazer início; Aberta -> Cancelada | ok | `test_c_ciclo_completo_historico_legivel_e_contadores` |
| Histórico com rótulos legíveis (nenhum nome de coluna) | ok | idem |
| Contadores 'Abertas' e 'Em execução' a cada passo | ok | idem |
| Filtros 'Abertas pela operação', status, 'Não visualizadas' | ok | `test_c_filtros_busca_e_escopo` |
| Busca 'balanca' acha 'Balança'; escopo Itens / Tudo | ok | idem |
| 'Visualizada': só a manutenção no detalhe; usuario, admin e listas não | ok | `test_c_visualizada_so_pela_manutencao_no_detalhe` |
| SLA 'No prazo', 'Vence em 10 min', 'Atrasada' com relógio trocado | ok | `test_c_etiquetas_de_sla_com_relogio` |
| Excluídas somem; restauradas voltam | ok | `test_a_admin_edita_concluida_cancela_exclui_e_restaura` |
| Relatório = conta à mão (3 abertas, 1 concluída, 1 cancelada; início 30 min; solução 120 min) | ok | `test_c_relatorio_bate_com_a_conta_a_mao` |

## Parte D — visual

`flet test` não roda aqui (precisa de numpy e do app de teste do Flutter); as telas foram
conferidas com Playwright/Chromium no app local (0 erros de página ou de console nas 12
execuções).

| Conferido no navegador | 360 | 390 | 800 | 1280 |
|---|---|---|---|---|
| Home com 22 ordens (topo e fim), admin / manutencao / usuario | ok | ok | ok | ok |
| Perfil (topo e fim), Aparelhos conectados com 0 aparelhos, sem e-mail | ok | ok | ok | ok |
| Nada embaixo da barra; último cartão tocável | ok | ok | ok | ok |
| Itens da barra centralizados no PC | — | — | ok | ok |
| Título longo quebra sem estragar o layout | ok | ok | ok | ok |
| Sem caixa cinza; acentos corretos; sem menção a e-mail | ok | ok | ok | ok |

Aparelhos conectados com 3 aparelhos: conferido no prompt 43 (390 e 1280 px). As demais
telas (Detalhe em cada status, formulários, Concluir, Relatórios, Lixeira, usuários, SLA)
ficam na lista manual abaixo.

## Erros

- **Corrigidos neste check-up:** nenhum.
- **Para a 2.0:**
  - Entrada de horas e valores 'dígitos pela direita' (regra atual diferente; ver Parte B).
    Na 2.0: máscara no navegador.
  - Os já listados em `docs/VERSAO_FLET_FINAL.md` ('Erros abertos').

## Parte E — lista manual (app publicado, celular e PC)

Faça no celular (vertical) e no PC. Marque cada item.

**Como usuario**
- [ ] Entrar como `usuario`: no primeiro acesso o app pede a troca de senha.
- [ ] Nova Solicitação: título, descrição, urgência; a filial não pode ser trocada.
- [ ] A lista mostra as ordens de todos na 1007 (de `usuario2` e da manutenção), sem
      valores (R$) e sem prioridade.
- [ ] Abrir uma ordem de outra pessoa: sem botão de alterar ou cancelar.
- [ ] Alterar e cancelar a própria solicitação enquanto Aberta funciona (cancelar pede
      motivo).
- [ ] Barra inferior sem 'Relatórios'; Perfil sem Usuários, SLA, Lixeira.

**Como usuario2**
- [ ] Abrir a solicitação do `usuario`: não aparece 'Alterar' nem 'Cancelar'.

**Como manutencao**
- [ ] Lista com valores (R$) e o filtro 'Não visualizadas'.
- [ ] Abrir a solicitação do `usuario`: ela passa a 'Visualizada' (o `usuario` vê isso
      no detalhe).
- [ ] 'Iniciar execução' mostra o que falta (tempo, tipo, especialidade, custo ou Sem
      gasto).
- [ ] Assumir: a prioridade já vem igual à urgência; a urgência não pode ser mudada.
- [ ] Preencher, adicionar um item (1,5 x 33,33 = R$ 50,00) e iniciar; a faixa muda
      (Abertas -1, Em execução +1).
- [ ] Nova OS direta com 'Sem gasto' no previsto; iniciar; concluir com 'Sem gasto' no
      realizado, horários e nota.
- [ ] Concluir sem nota ou sem realizado: mensagem de erro.

**Como manutencao2**
- [ ] Abrir a ordem iniciada por `manutencao`: sem 'Concluir' e sem 'Desfazer início'.

**Como admin**
- [ ] Nova Solicitação e Nova OS com a filial escolhível.
- [ ] Alterar uma ordem concluída (inclusive o realizado).
- [ ] Cancelar uma Aberta com motivo; excluir outra com motivo; ela aparece na Lixeira;
      restaurar: volta com o mesmo número.
- [ ] Usuários: criar, mudar filiais permitidas, redefinir senha (o usuário tem de trocar
      no próximo login), desativar (o usuário é barrado na próxima ação).
- [ ] SLA: mudar um prazo; especialidades e motivos de cancelamento: criar um.
- [ ] Relatórios: mês e acumulado sem erro, números coerentes com as ordens criadas.

**Em todas as telas, celular e PC**
- [ ] Nada fica escondido embaixo da barra inferior; o último cartão abre.
- [ ] Nenhum valor quebrado em duas linhas; acentos corretos; títulos longos quebram.
- [ ] Nenhuma caixa cinza; botões fáceis de tocar.
- [ ] Listas vazias mostram uma mensagem.
- [ ] Nenhuma menção a e-mail (Perfil, usuários, guia '?').
- [ ] Busca 'balanca' acha 'Balança'; busca pelo número da OS acha a ordem.
