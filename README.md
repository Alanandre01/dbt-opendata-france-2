# Data Engineering — Mois 2 : Cloud & Stockage

## Stack technique
AWS S3 · AWS Glue · Amazon Athena · Python · Parquet · dbt · Snowflake

## Architecture — Semaine 1

```
[data.gouv.fr CSV]
       │
       ▼
  Python (pandas + pyarrow)
  → Nettoyage + typage
  → Conversion Parquet
       │
       ▼
  S3 alan-data-lake-fr/
  ├── raw/dataset/           ← fichier CSV original
  └── staging/dataset/       ← Parquet partitionné
      └── annee=2026/mois=05/data.parquet
       │
       ▼
  AWS Glue Crawler
  → Détection automatique du schéma
  → Glue Data Catalog (alan_data_lake_db)
       │
       ▼
  Amazon Athena
  → SQL serverless sur Parquet
  → Résultats dans athena-results/
```

## Résultats mesurés

| Métrique | Valeur |
|---|---|
| Dataset source | Base SIRENE Nantes Métropole (data.gouv.fr) |
| Taille CSV original | 400.9 MB |
| Taille Parquet | 48.3 MB |
| **Ratio de compression** | **8.3x** |
| Nb lignes | 420 411 |
| Coût Athena (5 requêtes) | ~0.00$ |

## Pourquoi Parquet plutôt que CSV ?

Format colonnaire : lecture plus rapide sur requêtes analytiques.
Compression : **8.3x** fois plus léger que le CSV source.
Athena facture par données scannées — avec Parquet, le coût est bien inférieur.
Schéma intégré : plus de problèmes de typage à l'ingestion.

### Pourquoi ces 3 choix techniques

**`engine="pyarrow"`** — PyArrow sérialise colonne par colonne et encode les chaînes en dictionnaire, ce qui explique l'essentiel du ratio 8x sur un dataset SIRENE où 80 % des colonnes sont des catégories répétées (commune, section NAF, nature juridique).

**`compression="snappy"`** — Snappy privilégie la vitesse de décompression sur le taux de compression. C'est le bon compromis pour Athena ou Spark qui décompressent à la volée : un codec plus agressif (gzip, zstd) gagne quelques MB mais ralentit chaque requête.

**`index=False`** — L'index pandas est un artefact Python sans signification métier. L'inclure ajouterait une colonne entière au fichier et casserait les outils SQL (Athena, dbt) qui ne savent pas quoi en faire.

## Partitionnement Hive

Structure `annee=YYYY/mois=MM/` utilisée pour le partition pruning.
Une requête avec `WHERE annee=2026 AND mois='05'` ne scanne
que ce dossier — Athena ne lit pas les autres partitions.

Chemin actuel :
```
s3://alan-data-lake-fr/staging/base-sirene-nantes/annee=2026/mois=05/data.parquet
```

## Lifecycle Policy S3

| Délai | Transition | Classe de stockage |
|-------|------------|--------------------|
| J+0   | Dépôt initial | S3 Standard |
| J+30  | Accès rare | S3 Standard-IA |
| J+90  | Archivage | S3 Glacier |
| J+365 | Suppression | — |

Appliquée sur le préfixe `raw/` pour maîtriser les coûts de stockage sans intervention manuelle.
Les résultats Athena (`athena-results/`) sont supprimés automatiquement après 7 jours.

## Sécurité & RGPD

- IAM : principe du moindre privilège (user avec droits S3+Athena+Glue uniquement)
- MFA activé sur le compte root AWS
- Bucket S3 : accès public bloqué, encryption SSE-S3
- Lifecycle policy : archivage Glacier après 30 jours (conformité rétention RGPD)
- Région : eu-west-1 (Ireland) — données hébergées en Europe

## Commandes essentielles

```bash
# Vérifier les fichiers dans S3
aws s3 ls s3://alan-data-lake-fr/staging/ --recursive --human-readable

# Inspecter les métadonnées (taille, chiffrement, source)
aws s3api head-object \
  --bucket alan-data-lake-fr \
  --key staging/base-sirene-nantes/annee=2026/mois=05/data.parquet

# Lancer le Crawler Glue
aws glue start-crawler --name alan-staging-crawler

# Voir l'état du Crawler
aws glue get-crawler --name alan-staging-crawler --query 'Crawler.State'

# Convertir le CSV en Parquet et uploader sur S3
python convert_to_parquet.py

# Valider le fichier Parquet depuis S3
python validate_parquet.py
```

