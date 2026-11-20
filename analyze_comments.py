"""
=============================================================================
ANALISIS & PEMROSESAN DATA KOMENTAR FACEBOOK (BIG DATA PIPELINE)
=============================================================================
Skrip ini memproses hasil scraping dari 'facebook_comments.csv':
1. Data Cleaning: Menghapus noise, URL, karakter khusus, dan normalisasi spasi.
2. Metrik Komentar: Komentar terpopuler (top liked), rata-rata likes, panjang teks.
3. Analisis Frekuensi Kata (Word Frequency): Menemukan kata kunci teratas.
4. Export Hasil Analisis: Menyimpan laporan analisis ke CSV, JSON, dan SQLite DB.
=============================================================================
"""

import os
import re
import json
import sqlite3
import logging
from collections import Counter
from typing import Dict, Any, List, Optional
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("FacebookDataAnalyzer")

# Stopwords umum bahasa Indonesia untuk memfilter kata penghubung/tidak bermakna
INDONESIAN_STOPWORDS = {
    "yang", "di", "dan", "ini", "itu", "dari", "untuk", "pada", "ke", "karena",
    "dengan", "bisa", "ada", "juga", "sudah", "lagi", "sama", "aja", "nya", "ya",
    "ga", "gak", "nggak", "tak", "mau", "kalau", "kalo", "aku", "kamu", "dia",
    "mereka", "kita", "kami", "bang", "kak", "mas", "pak", "bu", "jadi", "sangat",
    "banget", "buat", "oleh", "dalam", "saat", "lebih", "tapi", "tetapi", "deh",
    "dong", "sih", "lah", "kok", "kan", "nih", "tuh", "pas", "si", "para", "bapak",
    "yg", "dgn", "utk", "sdh", "lg", "aja", "klo", "tp", "dr", "krn", "sy", "blm"
}

# Lexicon kata positif dan negatif sederhana
POSITIVE_LEXICON = {
    "bagus", "keren", "mantap", "hebat", "lucu", "ngakak", "suka", "terbaik",
    "semangat", "sukses", "kreatif", "menghibur", "terhibur", "senang", "terimakasih",
    "makasih", "mantul", "asli", "gokil", "juara", "salut", "top", "amanah",
    "berkah", "sehat", "adem", "bahagia", "ikhlas", "iklas", "peduli", "ramah",
    "panutan", "cerdas", "aamiin", "amin", "luar biasa"
}

NEGATIVE_LEXICON = {
    "jelek", "buruk", "kecewa", "bosan", "garing", "lebay", "aneh", "parah",
    "payah", "sampah", "rusak", "ngeselin", "benci", "skip", "kasar", "gajelas",
    "bohong", "hoax", "menyesal", "rugi", "pencitraan", "modus", "sandiwara",
    "palsu", "dusta", "korupsi", "omong kosong"
}


class FacebookCommentAnalyzer:
    """
    Kelas untuk membersihkan, mengekstrak wawasan, dan menganalisis teks komentar Facebook.
    """

    def __init__(self, csv_filepath: str = "facebook_comments.csv"):
        self.csv_filepath = csv_filepath
        self.df: Optional[pd.DataFrame] = None
        self.cleaned_df: Optional[pd.DataFrame] = None
        self.metrics: Dict[str, Any] = {}

    def load_data(self) -> pd.DataFrame:
        """Memuat dataset komentar dari file CSV."""
        if not os.path.exists(self.csv_filepath):
            raise FileNotFoundError(
                f"File '{self.csv_filepath}' tidak ditemukan! Pastikan Anda sudah menjalankan facebook_scraper.py."
            )

        logger.info(f"Memuat data dari: {self.csv_filepath}")
        self.df = pd.read_csv(self.csv_filepath, encoding="utf-8-sig")
        logger.info(f"Berhasil memuat {len(self.df)} baris data komentar Facebook.")
        return self.df

    @staticmethod
    def clean_text(text: str) -> str:
        """
        Membersihkan teks dari URL, mention akun (@user), simbol non-alfanumerik,
        dan spasi ganda.
        """
        if not isinstance(text, str):
            return ""

        # 1. Hapus URL / Link HTTP
        text = re.sub(r"https?://\S+|www\.\S+", "", text)
        # 2. Hapus mention akun (@user)
        text = re.sub(r"@\w+", "", text)
        # 3. Hapus karakter non-alfanumerik dan simbol (simpan huruf dan angka)
        text = re.sub(r"[^\w\s]", " ", text)
        # 4. Hapus angka tunggal
        text = re.sub(r"\b\d+\b", "", text)
        # 5. Normalisasi huruf kecil (lowercasing)
        text = text.lower()
        # 6. Hapus spasi berlebih
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def classify_sentiment(text: str) -> str:
        """
        Klasifikasi sentimen berbasis lexicon sederhana untuk bahasa Indonesia.
        Mengembalikan: 'Positif', 'Negatif', atau 'Netral'.
        """
        if not isinstance(text, str):
            return "Netral"
        words = set(text.lower().split())
        pos_count = len(words.intersection(POSITIVE_LEXICON))
        neg_count = len(words.intersection(NEGATIVE_LEXICON))

        if pos_count > neg_count:
            return "Positif"
        elif neg_count > pos_count:
            return "Negatif"
        return "Netral"

    def process_and_clean(self) -> pd.DataFrame:
        """Menjalankan tahap pembersihan teks pada seluruh baris komentar."""
        if self.df is None:
            self.load_data()

        logger.info("Menjalankan proses pembersihan teks (Data Cleaning)...")
        self.cleaned_df = self.df.copy()

        # Pastikan kolom like_count bernilai numerik
        if "like_count" in self.cleaned_df.columns:
            self.cleaned_df["like_count"] = pd.to_numeric(
                self.cleaned_df["like_count"], errors="coerce"
            ).fillna(0).astype(int)
        else:
            self.cleaned_df["like_count"] = 0

        # Tambahkan kolom teks bersih, panjang karakter, jumlah kata, dan sentimen
        self.cleaned_df["cleaned_text"] = self.cleaned_df["text"].apply(self.clean_text)
        self.cleaned_df["char_length"] = self.cleaned_df["text"].astype(str).str.len()
        self.cleaned_df["word_count"] = self.cleaned_df["cleaned_text"].apply(lambda x: len(x.split()))
        self.cleaned_df["sentiment"] = self.cleaned_df["cleaned_text"].apply(self.classify_sentiment)

        logger.info("Pembersihan data dan klasifikasi sentimen selesai.")
        return self.cleaned_df

    def compute_summary_statistics(self) -> Dict[str, Any]:
        """Menghitung metrik analitik dan statistik deskriptif dari komentar."""
        if self.cleaned_df is None:
            self.process_and_clean()

        df = self.cleaned_df
        total_comments = len(df)
        total_likes = int(df["like_count"].sum())
        avg_likes = float(df["like_count"].mean()) if total_comments > 0 else 0.0
        max_likes = int(df["like_count"].max()) if total_comments > 0 else 0

        # Cari 3 komentar terpopuler berdasarkan like
        top_liked_records = df.sort_values(by="like_count", ascending=False).head(3)
        top_comments = []
        for _, row in top_liked_records.iterrows():
            top_comments.append({
                "author": row.get("author", "N/A"),
                "likes": int(row.get("like_count", 0)),
                "text": str(row.get("text", ""))[:150]
            })

        # Hitung frekuensi kata terbanyak (Tokenization & Stopwords Filtering)
        all_words: List[str] = []
        for text in df["cleaned_text"]:
            words = text.split()
            filtered = [w for w in words if len(w) >= 3 and w not in INDONESIAN_STOPWORDS]
            all_words.extend(filtered)

        word_counts = Counter(all_words)
        top_20_words = [{"word": word, "frequency": count} for word, count in word_counts.most_common(20)]

        # Hitung persentase sentimen
        sentiment_counts = df["sentiment"].value_counts().to_dict()

        self.metrics = {
            "total_comments_analyzed": total_comments,
            "total_likes_on_comments": total_likes,
            "average_likes_per_comment": round(avg_likes, 2),
            "highest_likes_single_comment": max_likes,
            "average_word_count": round(float(df["word_count"].mean()), 2) if total_comments > 0 else 0.0,
            "sentiment_distribution": sentiment_counts,
            "top_3_liked_comments": top_comments,
            "top_20_frequent_words": top_20_words
        }

        return self.metrics

    def export_analysis_results(self, json_path: str = "comments_analysis_summary.json",
                                cleaned_csv_path: str = "cleaned_facebook_comments.csv") -> None:
        """Menyimpan ringkasan analisis ke JSON dan dataset hasil pembersihan ke CSV."""
        if not self.metrics:
            self.compute_summary_statistics()

        # Simpan CSV hasil pembersihan
        if self.cleaned_df is not None:
            self.cleaned_df.to_csv(cleaned_csv_path, index=False, encoding="utf-8-sig")
            logger.info(f"Dataset hasil pembersihan tersimpan di: {os.path.abspath(cleaned_csv_path)}")

        # Simpan Ringkasan Statistik ke JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.metrics, f, ensure_ascii=False, indent=4)
        logger.info(f"Ringkasan analitik tersimpan di: {os.path.abspath(json_path)}")

    def export_to_sqlite(self, db_path: str = "facebook_bigdata.db", table_name: str = "comments") -> None:
        """
        Menyimpan dataset komentar yang sudah dibersihkan ke database SQLite.
        Sangat cocok untuk demonstrasi query SQL pada tugas mata kuliah Big Data.
        """
        if self.cleaned_df is None:
            self.process_and_clean()

        try:
            conn = sqlite3.connect(db_path)
            self.cleaned_df.to_sql(table_name, conn, if_exists="replace", index=False)
            conn.close()
            logger.info(f"Data ({len(self.cleaned_df)} baris) berhasil disimpan ke SQLite DB: '{db_path}' (Tabel: '{table_name}')")
        except Exception as e:
            logger.error(f"Gagal menyimpan ke SQLite: {e}")


if __name__ == "__main__":
    CSV_FILE = "facebook_comments.csv"
    print("=" * 65)
    print("     ANALISIS & DATA CLEANING KOMENTAR FACEBOOK")
    print("=" * 65)

    if not os.path.exists(CSV_FILE):
        print(f"\n[PERINGATAN] File '{CSV_FILE}' belum tersedia.")
        print("Silakan jalankan scraper terlebih dahulu dengan perintah: python facebook_scraper.py\n")
    else:
        analyzer = FacebookCommentAnalyzer(CSV_FILE)
        stats = analyzer.compute_summary_statistics()

        print("\n=== METRIK STATISTIK KOMENTAR FACEBOOK ===")
        print(f"Total Komentar Dianalisis : {stats['total_comments_analyzed']}")
        print(f"Total Likes pada Komentar : {stats['total_likes_on_comments']:,}")
        print(f"Rata-rata Likes/Komentar  : {stats['average_likes_per_comment']}")
        print(f"Rata-rata Panjang Kata    : {stats['average_word_count']} kata")

        print("\n=== DISTRIBUSI SENTIMEN ===")
        for sent, count in stats.get("sentiment_distribution", {}).items():
            pct = (count / stats['total_comments_analyzed']) * 100
            print(f"- {sent:<10} : {count} komentar ({pct:.2f}%)")

        print("\n=== TOP 5 KATA YANG PALING SERING MUNCUL ===")
        for i, item in enumerate(stats["top_20_frequent_words"][:5], start=1):
            print(f"{i}. '{item['word']}' : muncul {item['frequency']} kali")

        print("\n=== KOMENTAR TERPOPULER (TOP LIKED) ===")
        for i, c in enumerate(stats["top_3_liked_comments"], start=1):
            print(f"[{i}] {c['author']} ({c['likes']} likes): \"{c['text']}\"")

        analyzer.export_analysis_results()
        analyzer.export_to_sqlite()
        print("\n[OK] Analisis selesai! File hasil disimpan ke 'cleaned_facebook_comments.csv', 'comments_analysis_summary.json', dan 'facebook_bigdata.db'.")
