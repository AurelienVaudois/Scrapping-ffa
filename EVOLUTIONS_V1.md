# Evolutions apportées - Version 1

## Objectif de cette version
Livrer une première version claire et exploitable de la visualisation des performances, avec comparaison optionnelle entre 2 athlètes, tout en conservant une interface simple.

## Evolutions fonctionnelles
- Passage de l’affichage principal vers Plotly (graphique interactif).
- Parcours principal simplifié: affichage d’un seul athlète par défaut.
- Comparaison activable à la demande avec un 2e athlète.
- Ajout de la superposition des performances des 2 athlètes sur un même graphique.
- Conservation des regroupements d’épreuves existants (100m à marathon, route, etc.).

## Evolutions UX / UI
- Réorganisation des contrôles dans la sidebar pour une lecture plus claire.
- Sections explicites: Athlète, Comparaison, Analyse, Avancé.
- Zone de sélection du 2e athlète placée juste sous la zone de comparaison.
- Séparation des commandes d’analyse: Axe X et Filtre performance.
- Choix du type de graphique: Nuage de points ou Lignes + points.
- Ajout d’un réglage de hauteur du graphique via un panneau avancé repliable.

## Evolutions de l’infobulle
- Champs conservés: performance, date, lieu, âge, type (indoor/outdoor).
- Ajout de la source de données: FFA ou World Athletics.
- Suppression des champs année et tour pour alléger la lecture.

## Evolutions data et robustesse
- Gestion du chargement/scraping pour le 2e athlète dans le flux de comparaison.
- Calcul de l’âge à partir de la date de performance et de l’année de naissance.
- Vérifications de cohérence effectuées après modifications (pas d’erreurs détectées dans le fichier de l’app).

## Résultat
La version 1 offre une expérience plus intuitive, plus lisible, et plus flexible, tout en conservant la richesse d’analyse déjà présente dans le projet.
