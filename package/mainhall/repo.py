from imporh import *

# Path tetap ke file repo.xlsx
REPO_FILE_PATH = "/home//ec2-user/package/repo.xlsx"

def load_repo_data():
    try:
        return pd.read_excel(REPO_FILE_PATH)
    except Exception:
        return None

@is_authorized_user
@spy
@vip    
@with_queue_control
async def repo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df = load_repo_data()
    if df is None:
        await update.message.reply_text("❌ Gagal membaca data repo.")
        return

    if len(context.args) == 0:
        # Daftar ticker unik
        tickers = sorted(set(df['Ticker'].dropna().unique()))
        message = "📄 Daftar Ticker dalam Repo:\n\n" + "\n".join(tickers)
        message += "\n\n📝 *Catatan:*\nGunakan /repo nama ticker untuk detail"
        await update.message.reply_text(message, parse_mode="Markdown")
        return

    ticker = context.args[0].upper()
    filtered = df[df['Ticker'].str.upper() == ticker]

    if filtered.empty:
        await update.message.reply_text(f"❌ Tidak ditemukan data repo untuk ticker {ticker}")
        return

    lines = [f"<pre>📊 Repo {ticker}:</pre>"]
    for _, row in filtered.iterrows():
        broker = str(row.get('Broker', '-'))
        jatuh_tempo = str(row.get('Jatuh Tempo', '-'))
        hutang = str(row.get('Hutang Repo', '-'))
        lines.append(f"<pre>{broker:<10} | {jatuh_tempo:<12} | {hutang:>12}</pre>")

    lines.append("<i>📝 Note: Hutang repo Broker KB Valbury, MNC dan Buana Capital dalam bentuk lembar saham</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    
    del df
    del filtered
    gc.collect()
