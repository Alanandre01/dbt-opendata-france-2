import sys
import pandas as pd
import boto3
from io import BytesIO
from dotenv import load_dotenv
import os

sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

BUCKET  = "alan-data-lake-fr"
S3_KEY  = "staging/base-sirene-nantes/annee=2026/mois=05/data.parquet"
REGION  = "eu-west-1"

print(f"Lecture depuis s3://{BUCKET}/{S3_KEY}")

s3  = boto3.client("s3", region_name=REGION)
obj = s3.get_object(Bucket=BUCKET, Key=S3_KEY)
df  = pd.read_parquet(BytesIO(obj["Body"].read()))

print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RAPPORT DE VALIDATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Dimensions    : {df.shape[0]:,} lignes x {df.shape[1]} colonnes
  Memoire       : {df.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB

TYPES DE COLONNES :
{df.dtypes.to_string()}

VALEURS MANQUANTES (colonnes avec >0 nulls) :
{df.isnull().sum()[df.isnull().sum() > 0].to_string() or "  Aucune valeur manquante"}

APERCU (5 premieres lignes) :
""")
print(df.head().to_string())

# Verification des colonnes de partition
for col in ["annee", "mois"]:
    if col in df.columns:
        print(f"\nColonne de partition '{col}' presente")
        print(f"   Valeurs uniques : {sorted(df[col].unique())}")
    else:
        print(f"\nColonne de partition '{col}' manquante")

print("\nValidation terminee — donnees pretes pour Snowflake")
