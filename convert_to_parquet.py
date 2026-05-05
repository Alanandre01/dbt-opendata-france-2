import os
import sys
import pandas as pd
import boto3
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv

# ── Chargement des variables d'environnement ──────────────────
load_dotenv()

BUCKET    = os.getenv("S3_BUCKET", "alan-data-lake-fr")
REGION    = os.getenv("AWS_DEFAULT_REGION", "eu-west-1")
CSV_PATH  = "data/raw/base-sirene-nantes.csv"
SEPARATOR = ";"
ENCODING  = "utf-8-sig"  # BOM présent dans la source data.gouv.fr

# Colonnes à typer (noms exacts dans le CSV)
DATE_COL   = "Date de création de l'établissement"
AMOUNT_COL = "Tranche de l'effectif de l'établissement triable"

# ── Étape 1 : Chargement du CSV ───────────────────────────────
print(f"Chargement de {CSV_PATH}...")
try:
    df = pd.read_csv(
        CSV_PATH,
        sep=SEPARATOR,
        encoding=ENCODING,
        low_memory=False
    )
except FileNotFoundError:
    print(f"Fichier introuvable : {CSV_PATH}")
    print("Place ton CSV dans data/raw/ et relance.")
    sys.exit(1)

csv_size_mb = os.path.getsize(CSV_PATH) / 1024 / 1024
print(f"{len(df):,} lignes chargées — CSV : {csv_size_mb:.1f} MB")
print(f"   Colonnes : {list(df.columns)}")

# ── Étape 2 : Nettoyage et typage ────────────────────────────
print("\nNettoyage des types...")

# Convertir la colonne date
if DATE_COL in df.columns:
    df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
    df["annee"]   = df[DATE_COL].dt.year.fillna(9999).astype("int32")
    df["mois"]    = df[DATE_COL].dt.month.fillna(99).astype("int32")
    print(f"Colonne date '{DATE_COL}' convertie")

# Convertir la colonne numérique si elle existe
if AMOUNT_COL and AMOUNT_COL in df.columns:
    df[AMOUNT_COL] = pd.to_numeric(df[AMOUNT_COL], errors="coerce")
    print(f"Colonne numérique '{AMOUNT_COL}' convertie")

# Supprimer les colonnes entièrement vides
cols_before = df.shape[1]
df = df.dropna(axis=1, how="all")
print(f"{cols_before - df.shape[1]} colonnes vides supprimées")

print(f"   Schéma final :\n{df.dtypes.to_string()}")

# ── Étape 3 : Conversion en Parquet en mémoire ───────────────
print("\nConversion en Parquet (compression Snappy)...")
buffer = BytesIO()
df.to_parquet(
    buffer,
    engine="pyarrow",
    compression="snappy",
    index=False
)
parquet_size_mb = buffer.tell() / 1024 / 1024
buffer.seek(0)

ratio = csv_size_mb / parquet_size_mb
print(f"CSV : {csv_size_mb:.1f} MB → Parquet : {parquet_size_mb:.1f} MB")
print(f"   Ratio de compression : {ratio:.1f}x plus petit 🎉")

# ── Étape 4 : Upload sur S3 avec partitionnement ────────────
print(f"\nUpload sur s3://{BUCKET}...")

# Construire la clé S3 avec partitionnement Hive
annee = datetime.now().year
mois  = f"{datetime.now().month:02d}"
s3_key = f"staging/base-sirene-nantes/annee={annee}/mois={mois}/data.parquet"

try:
    s3 = boto3.client("s3", region_name=REGION)
    s3.put_object(
        Bucket=BUCKET,
        Key=s3_key,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream",
        Metadata={
            "source": "data.gouv.fr",
            "rows": str(len(df)),
            "created_by": "alan-data-lake"
        }
    )
    print(f"Uploadé : s3://{BUCKET}/{s3_key}")
    print(f"   {len(df):,} lignes · {parquet_size_mb:.1f} MB")

except Exception as e:
    print(f"Erreur S3 : {e}")
    print("   Vérifie tes credentials AWS et les droits IAM.")
    sys.exit(1)

# ── Résumé final ────────────────────────────────────────────
print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 CONVERSION RÉUSSIE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Lignes traitées : {len(df):,}
  CSV original    : {csv_size_mb:.1f} MB
  Parquet Snappy  : {parquet_size_mb:.1f} MB
  Compression     : {ratio:.1f}x
  Destination S3  : s3://{BUCKET}/{s3_key}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
