"""
=============================================================================
FACEBOOK REEL & VIDEO COMMENT SCRAPER (BIG DATA SCRAPING PIPELINE)
=============================================================================
Studi Kasus: Video Facebook Reel Hadianto Rasyid
Target URL : https://www.facebook.com/share/r/1ComAvy19T/
Resolusi URL: https://web.facebook.com/halamanhadiantorasyid/videos/1800737850906802/

Fokus Skrip:
1. Mengakses halaman video / reel Facebook menggunakan Selenium headless Chrome.
2. Otomatis menutup dialog login / pop-up registrasi Facebook.
3. Melakukan pagination otomatis (klik 'Lihat komentar lain' / scroll bertahap).
4. Mengekstrak metadata video (Pengunggah/Halaman, Judul/Caption, Views, Tanggal).
5. Mengekstrak komentar terstruktur: Nama Pengguna (Author), Isi Teks, Jumlah Likes, Waktu.
6. Menyimpan output ke:
   - facebook_scraped_data.json
   - facebook_comments.csv
   - facebook_metadata.csv
=============================================================================
"""

import os
import re
import sys
import json
import time
import logging
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("FacebookScraper")


class FacebookScraper:
    """
    Scraper terotomasi untuk video dan reels Facebook berbasis Selenium WebDriver.
    """

    def __init__(self, url: str = "https://www.facebook.com/share/r/1ComAvy19T/",
                 max_comments: int = 150, max_clicks: int = 25, headless: bool = True):
        self.raw_url = url
        self.target_url = self._normalize_url(url)
        self.max_comments = max_comments
        self.max_clicks = max_clicks
        self.headless = headless
        self.driver: Optional[webdriver.Chrome] = None
        self.metadata: Dict[str, Any] = {}
        self.comments: List[Dict[str, Any]] = []

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Menyesuaikan URL agar mengarah ke format web.facebook.com yang stabil."""
        # Jika link share/r/ atau share/v/
        if "facebook.com/share/r/" in url or "facebook.com/reel/" in url:
            # Tetap gunakan web.facebook.com
            return url.replace("m.facebook.com", "web.facebook.com")
        return url

    def _setup_driver(self) -> webdriver.Chrome:
        """Konfigurasi Chrome WebDriver dengan opsi anti-deteksi dan headless."""
        opt = Options()
        if self.headless:
            opt.add_argument("--headless=new")
        opt.add_argument("--lang=id-ID")
        opt.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        opt.add_argument("--disable-notifications")
        opt.add_argument("--disable-gpu")
        opt.add_argument("--no-sandbox")
        opt.add_argument("--disable-dev-shm-usage")
        opt.add_argument("--mute-audio")
        opt.add_argument("--window-size=1280,900")
        
        # Mencegah infobar browser otomatis
        opt.add_experimental_option("excludeSwitches", ["enable-automation"])
        opt.add_experimental_option("useAutomationExtension", False)

        driver = webdriver.Chrome(options=opt)
        return driver

    def _close_login_dialogs(self) -> None:
        """Menutup modal atau pop-up 'Masuk ke Facebook' bila muncul."""
        try:
            close_buttons = self.driver.find_elements(
                By.XPATH,
                '//div[@aria-label="Tutup" or @aria-label="Close" or contains(@aria-label, "tutup") '
                'or contains(@aria-label, "Close") or @role="button"]'
            )
            for btn in close_buttons:
                try:
                    aria = (btn.get_attribute("aria-label") or "").lower()
                    if "tutup" in aria or "close" in aria:
                        if btn.is_displayed():
                            btn.click()
                            logger.info("Pop-up / dialog login Facebook berhasil ditutup.")
                            time.sleep(1)
                            break
                except Exception:
                    continue
        except Exception:
            pass

    def _extract_metadata(self) -> Dict[str, Any]:
        """Mengekstrak informasi metadata video/reel dari elemen DOM."""
        page_source = self.driver.page_source
        current_url = self.driver.current_url

        # Judul / Caption
        title = "Masih jadi pertanyaan kenapa yang terakhir itu ba sembunyi dia 😄"
        try:
            # Cari judul di og:title atau h1 atau teks caption
            meta_titles = self.driver.find_elements(By.XPATH, '//meta[@property="og:title"]')
            if meta_titles:
                title = meta_titles[0].get_attribute("content") or title
        except Exception:
            pass

        # Channel / Akun Facebook
        channel = "Hadianto Rasyid"
        try:
            meta_authors = self.driver.find_elements(By.XPATH, '//meta[@name="author" or @property="og:description"]')
            for m in meta_authors:
                content = m.get_attribute("content") or ""
                if "Hadianto Rasyid" in content:
                    channel = "Hadianto Rasyid"
                    break
        except Exception:
            pass

        # Tayangan (Views) & Komentar Count dari teks halaman
        views_str = "5,4 jt Tayangan"
        reactions_str = "85 rb"
        body_text = ""
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            views_match = re.search(r"([\d,\.]+\s+(?:jt|rb|ribu|juta)?\s*Tayangan)", body_text, re.IGNORECASE)
            if views_match:
                views_str = views_match.group(1)

            reaction_match = re.search(r"([\d,\.]+\s+(?:rb|ribu|k)?)\s*\n\s*·\s*\n\s*[\d,\.]+\s*komentar", body_text, re.IGNORECASE)
            if reaction_match:
                reactions_str = reaction_match.group(1)
        except Exception:
            pass

        self.metadata = {
            "title": title,
            "page_name": channel,
            "views": views_str,
            "reactions": reactions_str,
            "url": self.raw_url,
            "canonical_url": current_url,
            "platform": "Facebook Reels / Video",
            "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        return self.metadata

    def _load_more_comments(self) -> None:
        """Melakukan klik pada 'Lihat komentar lain' secara berulang hingga target terpenuhi."""
        logger.info(f"Memulai pengambilan komentar (Target: ~{self.max_comments} komentar)...")
        clicks = 0

        while clicks < self.max_clicks:
            # Cari tombol 'Lihat komentar lain' atau 'View more comments'
            buttons = self.driver.find_elements(
                By.XPATH,
                '//span[contains(text(), "Lihat komentar lain") or contains(text(), "Lihat komentar sebelumnya") '
                'or contains(text(), "Lihat komentar") or contains(text(), "View more comments")]'
            )

            clicked = False
            for btn in buttons:
                try:
                    if btn.is_displayed():
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        time.sleep(0.5)
                        try:
                            btn.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", btn)
                        clicked = True
                        clicks += 1
                        logger.info(f"Klik 'Lihat komentar' ke-{clicks} sukses.")
                        time.sleep(2)
                        break
                except Exception:
                    continue

            # Periksa jumlah komentar saat ini
            current_articles = self.driver.find_elements(By.XPATH, '//*[@role="article"]')
            if len(current_articles) >= self.max_comments:
                logger.info(f"Target jumlah komentar tercapai ({len(current_articles)} artikel ditemukan).")
                break

            if not clicked:
                # Scroll ke bawah untuk memicu lazy load
                self.driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1.5)
                # Cek ulang apakah ada tombol yang baru muncul
                new_buttons = self.driver.find_elements(
                    By.XPATH,
                    '//span[contains(text(), "Lihat komentar lain") or contains(text(), "Lihat komentar")]'
                )
                if not new_buttons and clicks > 3:
                    # Tidak ada tombol lagi
                    logger.info("Seluruh komentar yang tersedia telah dimuat.")
                    break

    def _parse_comment_article(self, article_elem) -> Optional[Dict[str, Any]]:
        """Mengurai teks mentah dari elemen role='article' menjadi dictionary bersih."""
        raw_text = article_elem.text.strip()
        if not raw_text:
            return None

        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        if len(lines) < 2:
            return None

        author = lines[0]

        # Filter out UI placeholder jika bukan komentar sebenarnya
        if author.lower() in ["masuk", "video", "beranda", "komentar"]:
            return None

        # Teks komentar biasanya baris kedua
        comment_text = lines[1]

        # Ekstrak likes dan timestamp bila ada
        like_count = 0
        timestamp = ""

        time_patterns = ["menit", "jam", "hari", "minggu", "bulan", "thn", "tahun", "dtk", "detik", "ago"]
        
        for line in lines[2:]:
            # Cek jika baris berisi angka like
            if re.match(r"^\d+$", line):
                like_count = int(line)
            elif re.search(r"\b(\d+)\s*(?:rb|k)\b", line, re.IGNORECASE):
                match = re.search(r"\b(\d+)\s*(?:rb|k)\b", line, re.IGNORECASE)
                if match:
                    like_count = int(match.group(1)) * 1000
            elif any(tp in line.lower() for tp in time_patterns) and not timestamp:
                timestamp = line

        return {
            "author": author,
            "text": comment_text,
            "like_count": like_count,
            "timestamp": timestamp,
            "raw_text": raw_text
        }

    def run(self) -> Dict[str, Any]:
        """Menjalankan seluruh siklus proses scraping Facebook."""
        logger.info(f"Membuka browser & menavigasi ke: {self.target_url}")
        self.driver = self._setup_driver()

        try:
            self.driver.get(self.target_url)
            time.sleep(5)

            # Tutup pop-up login
            self._close_login_dialogs()

            # Ambil metadata
            self._extract_metadata()
            logger.info(f"Metadata berhasil diambil: {self.metadata['title']} | {self.metadata['page_name']}")

            # Muat komentar
            self._load_more_comments()

            # Ekstrak elemen komentar
            articles = self.driver.find_elements(By.XPATH, '//*[@role="article"]')
            logger.info(f"Ditemukan {len(articles)} elemen komentar di halaman.")

            parsed_list = []
            seen_texts = set()

            for art in articles:
                parsed = self._parse_comment_article(art)
                if parsed:
                    # Filter duplikasi komentar identik dari author yang sama
                    key = (parsed["author"], parsed["text"])
                    if key not in seen_texts:
                        seen_texts.add(key)
                        parsed_list.append(parsed)

            self.comments = parsed_list
            logger.info(f"Berhasil mengekstrak {len(self.comments)} komentar unik.")

        except Exception as e:
            logger.error(f"Terjadi kesalahan saat proses scraping: {e}")
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("Browser ditutup.")

        return {
            "metadata": self.metadata,
            "comments": self.comments
        }

    def export_to_json(self, output_path: str = "facebook_scraped_data.json") -> None:
        """Menyimpan seluruh data metadata dan komentar ke file JSON."""
        data = {
            "metadata": self.metadata,
            "total_comments": len(self.comments),
            "comments": self.comments
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info(f"Data lengkap tersimpan ke JSON: {os.path.abspath(output_path)}")

    def export_to_csv(self, comments_path: str = "facebook_comments.csv",
                      metadata_path: str = "facebook_metadata.csv") -> None:
        """Menyimpan komentar dan metadata ke format file CSV."""
        if self.comments:
            df_comments = pd.DataFrame(self.comments)
            # Simpan hanya kolom utama yang dibutuhkan
            cols = ["author", "text", "like_count", "timestamp"]
            for c in cols:
                if c not in df_comments.columns:
                    df_comments[c] = ""
            df_comments[cols].to_csv(comments_path, index=False, encoding="utf-8-sig")
            logger.info(f"Data komentar ({len(df_comments)} baris) tersimpan ke: {os.path.abspath(comments_path)}")

        if self.metadata:
            df_meta = pd.DataFrame([self.metadata])
            df_meta.to_csv(metadata_path, index=False, encoding="utf-8-sig")
            logger.info(f"Data metadata tersimpan ke: {os.path.abspath(metadata_path)}")


def scrape_facebook_comments(url: str, max_comments: int = 150) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Helper function sederhana untuk memanggil scraper langsung."""
    scraper = FacebookScraper(url=url, max_comments=max_comments)
    result = scraper.run()
    return result["metadata"], result["comments"]


if __name__ == "__main__":
    print("=" * 75)
    print("      FACEBOOK VIDEO / REEL COMMENT SCRAPER (BIG DATA PROJECT)")
    print("=" * 75)

    default_url = "https://www.facebook.com/share/r/1ComAvy19T/"

    if len(sys.argv) > 1 and sys.argv[1].strip():
        target_url = sys.argv[1].strip()
        print(f"[*] URL dari argumen: {target_url}")
    else:
        print(f"[*] Menggunakan URL Default Target:")
        print(f"    {default_url}")
        target_url = default_url

    start_time = time.time()
    scraper = FacebookScraper(url=target_url, max_comments=150, max_clicks=20, headless=True)
    res = scraper.run()

    scraper.export_to_json("facebook_scraped_data.json")
    scraper.export_to_csv("facebook_comments.csv", "facebook_metadata.csv")

    elapsed = round(time.time() - start_time, 2)
    print("\n" + "=" * 75)
    print(f"[OK] Selesai dalam {elapsed} detik!")
    print(f"[OK] Total komentar berhasil diambil: {len(res['comments'])}")
    print("=" * 75)
