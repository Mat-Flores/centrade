# Vocabulaire de l'interface

Règle (révisée le 13 octobre 2026, à la demande de l'opérateur) : un terme technique s'affiche en anglais, tel que les traders l'emploient, et s'explique en français au survol. Les mots courants, les actions et les commandes de sécurité restent en français.

## Termes affichés en anglais

| À l'écran | Explication au survol |
| --- | --- |
| Dry-run, Live, Backtest | Mode test, mode réel, rejeu d'une période passée. |
| Provider | Le moteur de trading qui fait tourner l'instance. |
| Timeframe | Unité de temps : la durée d'une bougie. |
| Stop-loss, Take-profit, Trailing stop | Politique de sortie d'une stratégie. |
| Realized PnL, Unrealized PnL | Résultat encaissé ; résultat en cours. |
| Wins, Losses, Win rate, Profit factor, Expectancy, Average win, Average loss, Best trade, Worst trade | Indicateurs de performance. |
| Max drawdown, Drawdown, Exposure, Stop distance | Indicateurs de risque. |
| Open positions, Fees, Stake, Slippage | Activité et coûts. |
| Sharpe ratio, Sortino ratio, Calmar ratio | Ratios. |

Restent en français : Solde, Achat, Vente, Gain, Perte, En cours, Arrêt d'urgence, Tout vendre, Mettre en pause les achats, Passer en réel.

« Constaté il y a 12 s » devient « Mis à jour il y a 12 s » (« Mis à jour à l'instant » sous 5 secondes), avec l'explication au survol : heure de la dernière réponse du bot.

Le tableau ci-dessous garde la correspondance avec le glossaire du SPEC ; sa première colonne date de la règle précédente.

## Mots gardés tels quels

bot, trade, backtest, stop-loss, take-profit, live (en infobulle de « mode réel »), paire, stratégie, instance, journal.

## Correspondance

| À l'écran | Terme du glossaire (`SPEC.md` §2) | Infobulle |
| --- | --- | --- |
| Mode test | paper, dry-run | Le bot trade avec de l'argent fictif. Tous les chiffres sont simulés. |
| Mode réel | live | Le bot trade avec l'argent du compte. |
| Backtest | backtest | Le bot rejoue une période passée. Un backtest n'est pas une prévision. |
| Achat | entrée (`entry`) | Ouverture d'une position. |
| Vente | sortie (`exit`) | Fermeture d'une position. |
| Stop-loss | stop protecteur | Prix auquel la position est vendue pour limiter la perte. |
| Take-profit | objectif de gain | Prix auquel la position est vendue pour encaisser le gain. |
| Gain, perte | PnL | Résultat d'un trade, frais déduits. |
| Encaissé | PnL réalisé | Résultat des trades terminés, frais déduits. |
| En cours | PnL latent | Résultat des positions encore ouvertes, au dernier prix observé. |
| Solde | equity | Valeur du compte de l'instance, positions ouvertes comprises. |
| Plus forte baisse | drawdown maximal | Plus grand recul du solde depuis un sommet. |
| Taux de réussite | win rate | Part des trades terminés en gain. |
| Rapport gains/pertes | profit factor | Somme des gains divisée par la somme des pertes. |
| Gain moyen par trade | espérance | Résultat moyen d'un trade, gains et pertes confondus. |
| Capital engagé | exposition | Part du solde placée dans des positions ouvertes. |
| Unité de temps | timeframe | Durée d'une bougie du graphique. |
| Mettre en pause les achats | `pause_entries`, sorties seules | Le bot n'achète plus, mais continue de gérer et de vendre ses positions. |
| Tout vendre | `flatten` | Vend toutes les positions au prix du marché. |
| Arrêt d'urgence | kill switch | Bloque tous les achats. Les ventes continuent. |
| Achat refusé | rejet de risque | Une protection a refusé l'achat. |
| Demandé | état voulu | Ce qui a été demandé au bot. |
| Constaté | état observé | Ce que le bot rapporte réellement, avec l'heure. |
| Périmé | au-delà du seuil de fraîcheur | La dernière valeur reçue est trop ancienne pour être fiable. |
| Version | version, empreinte de déploiement | Chaque modification de l'instance crée une nouvelle version. |
| Compte | compte, venue | Le compte d'exchange utilisé par l'instance. |
| Clé | clé API | Accès au compte d'exchange. Jamais ré-affichée après saisie. |
| Passer en réel | promotion | Crée une copie réelle de l'instance après une liste de contrôles. |
| Importer les données | `download-data` | Télécharge l'historique des prix nécessaire au backtest. |
| Coûts | frais, slippage | Frais de l'exchange et écart de prix à l'exécution. |

## Causes de vente

| À l'écran | Valeur canonique (F10) |
| --- | --- |
| Objectif atteint | `take_profit` |
| Stop | `stop_loss` |
| Stop suiveur | `trailing_stop` |
| Signal de la stratégie | `signal` |
| Délai dépassé | `timeout` |
| Manuel | `manual` |
| Arrêt d'urgence | `kill_switch` |
| Protection du bot | `engine_protection` |
| Inconnue | `unknown` |
