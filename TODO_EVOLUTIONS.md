# TODO - Evolutions ultérieures

## Légende de priorisation
- Must have: indispensable.
- Should have: très important.
- Could have: confortable à avoir.
- Won't have: hors périmètre de cette version.

## Légende de complexité
- S: simple, donnée déjà prête, visuel standard.
- M: préparation modérée ou visuel légèrement personnalisé.
- L: transformations lourdes ou logique complexe.
- XL: donnée non disponible ou développement spécifique important.

## Backlog (non classé par importance)
| # | Tâche | MoSCoW | Complexité (T-Shirt) | Notes |
|---|---|---|---|---|
| 4 | Créer un script de mise à jour de la base avec les nouveaux résultats | Should | S | ✅ Fait - script incrémental idempotent + loop + logs |
| 10 | N’afficher le volet déroulant que pour les épreuves avec performances disponibles | Should | M | ✅ Fait |
| 1 | Vérifier l’affichage sur téléphone et créer une version spécifique si nécessaire | Should | L | 🔄 En cours |
| 2 | Améliorer le scraping FFA (nom + prénom): éviter le fallback WA trop tôt pour les profils licenciés en France | Should | L | ✅ Fait |
| 9 | Mettre en place un monitoring de l’app (usage, vitesse) sur Streamlit Cloud puis sur autre provider si nécessaire | Should | L | 🔄 En cours - instrumentation + protocole de charge ajoutés |
| 5 | Ajouter de nouvelles distances (1000m, 110m haies, 400m haies) | Could | S |  |
| 3 | Optimiser la vitesse de scraping | Could | M |  |
| 6 | Ajouter les sauts et les lancers | Could | M |  |
| 7 | Ajouter des stats descriptives sous le graphe | Won't | S |  |
| 8 | Ajouter un module de forecast athlète | Won't | XL |  |

## Recommandation format
Le format Markdown est adapté pour un backlog léger, versionnable dans Git, et simple à relire.
Si tu veux aller plus loin (tri, vues, filtres, scoring), on pourra migrer ce tableau vers un format de pilotage (Notion/Jira/Linear) tout en gardant ce fichier comme source de vérité technique.
