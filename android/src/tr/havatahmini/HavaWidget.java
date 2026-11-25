package tr.havatahmini;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.time.LocalDate;

public class HavaWidget extends AppWidgetProvider {
    static final String URL_ADRES = "https://raw.githubusercontent.com/elektroboard/hava-tahmini-veri/main/tahmin.json";
    static final String ACT_SEHIR = "tr.havatahmini.SEHIR";
    static final String ACT_YENILE = "tr.havatahmini.YENILE";
    static final String[] GUN = {"Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"};
    static final String[] GUN_UZUN = {"Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"};
    static final int BG = 0xFF161B22, YAZI = 0xFFE8ECF1, SOLUK = 0xFF8F9BAB, CIZGI = 0xFF2C3440;
    static final int GUNES = 0xFFF5B335, BULUT = 0xFFAAB4C2, BULUT2 = 0xFF7D8898, DAMLA = 0xFF4AA3FF, KAR = 0xFFDCE8F5, SIMSEK = 0xFFF5C542;
    static final int W = 800, H = 460;

    @Override
    public void onUpdate(Context ctx, AppWidgetManager m, int[] ids) {
        ciz(ctx, m, ids);
        yenileArkada(ctx, false);
    }

    @Override
    public void onReceive(Context ctx, Intent in) {
        String a = in.getAction();
        android.util.Log.i("HAVA", "onReceive " + a);
        if (ACT_SEHIR.equals(a)) {
            SharedPreferences p = ctx.getSharedPreferences("hava", Context.MODE_PRIVATE);
            p.edit().putInt("sehir_no", p.getInt("sehir_no", 0) + 1).apply();
            ciz(ctx, AppWidgetManager.getInstance(ctx), hepsi(ctx));
            android.widget.Toast.makeText(ctx, "Şehir: " + sehirAdi(ctx), android.widget.Toast.LENGTH_SHORT).show();
        } else if (ACT_YENILE.equals(a)) {
            android.widget.Toast.makeText(ctx, "Yenileniyor…", android.widget.Toast.LENGTH_SHORT).show();
            yenileArkada(ctx, true);
        } else {
            super.onReceive(ctx, in);
        }
    }

    static String sehirAdi(Context ctx) {
        try {
            SharedPreferences pr = ctx.getSharedPreferences("hava", Context.MODE_PRIVATE);
            JSONObject sh = new JSONObject(pr.getString("json", "{}")).getJSONObject("sehirler");
            JSONArray n = sh.names();
            java.util.ArrayList<String> l = new java.util.ArrayList<>();
            for (int i = 0; i < n.length(); i++) l.add(n.getString(i));
            java.util.Collections.sort(l);
            int no = ((pr.getInt("sehir_no", 0) % l.size()) + l.size()) % l.size();
            return sh.getJSONObject(l.get(no)).getString("ad") + " (" + (no + 1) + "/" + l.size() + ")";
        } catch (Exception e) {
            return "veri yok";
        }
    }

    static int[] hepsi(Context ctx) {
        return AppWidgetManager.getInstance(ctx).getAppWidgetIds(new ComponentName(ctx, HavaWidget.class));
    }

    static boolean indir(Context ctx) {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(URL_ADRES + "?t=" + System.currentTimeMillis()).openConnection();
            c.setConnectTimeout(10000);
            c.setReadTimeout(15000);
            InputStream is = c.getInputStream();
            ByteArrayOutputStream o = new ByteArrayOutputStream();
            byte[] b = new byte[8192];
            int n;
            while ((n = is.read(b)) > 0) o.write(b, 0, n);
            String js = o.toString("UTF-8");
            new JSONObject(js);
            ctx.getSharedPreferences("hava", Context.MODE_PRIVATE).edit().putString("json", js).putLong("indirilme", System.currentTimeMillis()).putString("hata", "").apply();
            anlikIndir(ctx, new JSONObject(js));
            return true;
        } catch (Exception e) {
            android.util.Log.e("HAVA", "indir", e);
            ctx.getSharedPreferences("hava", Context.MODE_PRIVATE).edit().putString("hata", String.valueOf(e)).apply();
            return false; // internet yoksa son kaydedilen veri gösterilir
        }
    }

    static void anlikIndir(Context ctx, JSONObject kok) {
        SharedPreferences.Editor ed = ctx.getSharedPreferences("hava", Context.MODE_PRIVATE).edit();
        try {
            JSONObject sh = kok.getJSONObject("sehirler");
            java.util.Iterator<String> it = sh.keys();
            while (it.hasNext()) {
                String k = it.next();
                JSONObject b = sh.getJSONObject(k);
                if (!b.has("lat")) continue;
                try {
                    HttpURLConnection c = (HttpURLConnection) new URL("https://api.open-meteo.com/v1/forecast?latitude=" + b.getDouble("lat")
                            + "&longitude=" + b.getDouble("lon") + "&current=temperature_2m,apparent_temperature,weather_code,precipitation&timezone=Europe%2FIstanbul").openConnection();
                    c.setConnectTimeout(8000);
                    c.setReadTimeout(10000);
                    InputStream is = c.getInputStream();
                    ByteArrayOutputStream o = new ByteArrayOutputStream();
                    byte[] buf = new byte[4096];
                    int n;
                    while ((n = is.read(buf)) > 0) o.write(buf, 0, n);
                    JSONObject cur = new JSONObject(o.toString("UTF-8")).getJSONObject("current");
                    cur.put("alindi", System.currentTimeMillis());
                    ed.putString("anlik_" + k, cur.toString());
                } catch (Exception e) {
                    android.util.Log.e("HAVA", "anlik", e);
                }
            }
        } catch (Exception e) {
            // ana tahmin etkilenmez
        }
        ed.apply();
    }

    static String kodTur(int k) {
        if (k == 0) return "gunes";
        if (k == 1) return "az-bulut";
        if (k == 2) return "parcali";
        if (k == 3) return "bulut";
        if (k == 45 || k == 48) return "sis";
        if (k >= 95) return "firtina";
        if (k == 71 || k == 73 || k == 75 || k == 77 || k == 85 || k == 86) return "kar";
        if (k >= 51) return "yagmur";
        return "bulut";
    }

    static String kodAd(int k) {
        switch (kodTur(k)) {
            case "gunes": return "Açık";
            case "az-bulut": return "Az bulutlu";
            case "parcali": return "Parçalı bulutlu";
            case "yagmur": return (k >= 80 ? "Sağanak" : "Yağmurlu");
            case "kar": return "Karlı";
            case "firtina": return "Gök gürültülü";
            case "sis": return "Sisli";
            default: return "Bulutlu";
        }
    }

    void yenileArkada(final Context ctx, final boolean haber) {
        final BroadcastReceiver.PendingResult sonuc = goAsync();
        new Thread(() -> {
            boolean tamam = indir(ctx);
            try {
                ciz(ctx, AppWidgetManager.getInstance(ctx), hepsi(ctx));
                if (haber) {
                    final String msg = tamam ? "Güncellendi" : "İnternete bağlanılamadı, eski veri gösteriliyor";
                    new android.os.Handler(android.os.Looper.getMainLooper()).post(() ->
                            android.widget.Toast.makeText(ctx, msg, android.widget.Toast.LENGTH_SHORT).show());
                }
            } finally {
                sonuc.finish();
            }
        }).start();
    }

    static PendingIntent dugme(Context ctx, String act, int kod) {
        Intent i = new Intent(ctx, HavaWidget.class).setAction(act);
        return PendingIntent.getBroadcast(ctx, kod, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    static void ciz(Context ctx, AppWidgetManager m, int[] ids) {
        if (ids == null || ids.length == 0) return;
        Bitmap bmp = Bitmap.createBitmap(W, H, Bitmap.Config.ARGB_8888);
        try {
            cizBitmap(new Canvas(bmp), ctx);
        } catch (Exception e) {
            Canvas c = new Canvas(bmp);
            hata(c, "Veri okunamadı. Dokunarak yenileyin.");
        }
        for (int id : ids) {
            RemoteViews rv = new RemoteViews(ctx.getPackageName(), R.layout.widget);
            rv.setImageViewBitmap(R.id.resim, bmp);
            rv.setOnClickPendingIntent(R.id.kok, dugme(ctx, ACT_YENILE, 1));
            rv.setOnClickPendingIntent(R.id.sehir_dugme, dugme(ctx, ACT_SEHIR, 2));
            m.updateAppWidget(id, rv);
        }
    }

    static Paint boya(int renk, float boyut, boolean kalin) {
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        p.setColor(renk);
        p.setTextSize(boyut);
        p.setTypeface(kalin ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
        return p;
    }

    static void zemin(Canvas c) {
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        p.setColor(BG);
        c.drawRoundRect(new RectF(0, 0, W, H), 44, 44, p);
    }

    static void hata(Canvas c, String s) {
        zemin(c);
        Paint p = boya(SOLUK, 34, false);
        p.setTextAlign(Paint.Align.CENTER);
        c.drawText(s, W / 2f, H / 2f, p);
    }

    static void cizBitmap(Canvas c, Context ctx) throws Exception {
        SharedPreferences pr = ctx.getSharedPreferences("hava", Context.MODE_PRIVATE);
        String js = pr.getString("json", null);
        if (js == null) {
            hata(c, "Veri yok. Dokunarak yenileyin.");
            return;
        }
        JSONObject kok = new JSONObject(js);
        JSONObject sehirler = kok.getJSONObject("sehirler");
        JSONArray anahtar = sehirler.names();
        if (anahtar == null || anahtar.length() == 0) {
            hata(c, "Tahmin bulunamadı.");
            return;
        }
        java.util.ArrayList<String> liste = new java.util.ArrayList<>();
        for (int i = 0; i < anahtar.length(); i++) liste.add(anahtar.getString(i));
        java.util.Collections.sort(liste);
        int no = ((pr.getInt("sehir_no", 0) % liste.size()) + liste.size()) % liste.size();
        JSONObject sehir = sehirler.getJSONObject(liste.get(no));
        JSONArray g = sehir.getJSONArray("gunler");
        zemin(c);
        c.drawText(sehir.getString("ad") + (liste.size() > 1 ? "  ›" : ""), 36, 58, boya(YAZI, 40, true));
        String gun = kok.optString("guncelleme", "");
        Paint ust = boya(SOLUK, 22, false);
        ust.setTextAlign(Paint.Align.RIGHT);
        c.drawText(gun.length() >= 16 ? "tahmin " + gun.substring(11, 16) : "", W - 36, 54, ust);
        long ind = pr.getLong("indirilme", 0);
        if (ind > 0) {
            Paint tp = boya(SOLUK, 20, false);
            tp.setTextAlign(Paint.Align.RIGHT);
            c.drawText("yenilendi " + new java.text.SimpleDateFormat("HH:mm", java.util.Locale.US).format(new java.util.Date(ind)), W - 36, 80, tp);
        }
        JSONObject cur = null;
        String an = pr.getString("anlik_" + liste.get(no), null);
        if (an != null) {
            JSONObject o = new JSONObject(an);
            if (System.currentTimeMillis() - o.optLong("alindi", 0) < 3 * 3600_000L) cur = o;
        }
        c.drawText("Şu an", 250, 112, boya(SOLUK, 28, false));
        if (cur != null) {
            int kod = cur.optInt("weather_code", 3);
            ikon(c, 20, 66, 200, kodTur(kod));
            c.drawText(Math.round(cur.getDouble("temperature_2m")) + "°", 246, 206, boya(YAZI, 110, true));
            c.drawText(kodAd(kod), 250, 248, boya(YAZI, 32, false));
            if (cur.has("apparent_temperature"))
                c.drawText("hissedilen " + Math.round(cur.getDouble("apparent_temperature")) + "°", 250, 286, boya(SOLUK, 26, false));
        } else {
            c.drawText("—", 246, 206, boya(SOLUK, 110, true));
            c.drawText("Şu anki hava alınamadı", 250, 248, boya(SOLUK, 28, false));
        }
        JSONObject y0 = g.getJSONObject(0);
        Paint yp = boya(SOLUK, 24, false);
        yp.setTextAlign(Paint.Align.RIGHT);
        JSONObject mb = sehir.optJSONObject("mgm_bugun");
        JSONObject ub = sehir.optJSONObject("usta_bugun");
        Paint yb = boya(YAZI, 32, true);
        yb.setTextAlign(Paint.Align.RIGHT);
        float y = 112;
        if (mb != null || ub != null) {
            c.drawText("Bugün", W - 36, y, yp);
            y += 36;
            if (ub != null) {
                c.drawText("USTA  " + ub.getInt("en_dusuk") + "° / " + ub.getInt("en_yuksek") + "°", W - 36, y, yb);
                y += 36;
            }
            if (mb != null) {
                c.drawText("MGM  " + mb.getInt("en_dusuk") + "° / " + mb.getInt("en_yuksek") + "°", W - 36, y, yb);
                y += 32;
            }
            c.drawText("Yarın", W - 36, y, yp);
            y += 32;
        } else {
            c.drawText("Yarın için", W - 36, y, yp);
            y += 48;
        }
        Paint yk = boya(YAZI, 28, true);
        yk.setTextAlign(Paint.Align.RIGHT);
        c.drawText("USTA  " + y0.getInt("en_dusuk") + "° / " + y0.getInt("en_yuksek") + "°", W - 36, y, yk);
        if (!y0.isNull("mgm_en_yuksek"))
            c.drawText("MGM  " + y0.getInt("mgm_en_dusuk") + "° / " + y0.getInt("mgm_en_yuksek") + "°", W - 36, y + 32, yk);
        Paint cz = new Paint();
        cz.setColor(CIZGI);
        cz.setStrokeWidth(2);
        c.drawLine(36, 300, W - 36, 300, cz);
        float kw = (W - 72) / 6f;
        for (int i = 0; i < 6 && i < g.length(); i++) {
            JSONObject r = g.getJSONObject(i);
            float cx = 36 + i * kw + kw / 2;
            int d = LocalDate.parse(r.getString("tarih")).getDayOfWeek().getValue() - 1;
            Paint ad = boya(i == 0 ? YAZI : SOLUK, 26, i == 0);
            ad.setTextAlign(Paint.Align.CENTER);
            c.drawText(i == 0 ? "Yarın" : GUN[d], cx, 332, ad);
            ikon(c, cx - 32, 338, 64, r.getString("tur"));
            Paint mx = boya(YAZI, 30, true);
            mx.setTextAlign(Paint.Align.CENTER);
            c.drawText(r.getInt("en_yuksek") + "°", cx - 22, 424, mx);
            Paint mn = boya(SOLUK, 24, false);
            mn.setTextAlign(Paint.Align.CENTER);
            c.drawText(r.getInt("en_dusuk") + "°", cx + 32, 424, mn);
            if (!r.isNull("yagis") && r.getInt("yagis") >= 30) {
                Paint yg = boya(DAMLA, 21, false);
                yg.setTextAlign(Paint.Align.CENTER);
                c.drawText("%" + r.getInt("yagis"), cx, 452, yg);
            }
        }
    }

    // ---- ikonlar (s piksellik kare, (x, y) sol üst) ----
    static void daire(Canvas c, int renk, float x, float y, float s, float cx, float cy, float r) {
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        p.setColor(renk);
        c.drawCircle(x + cx * s, y + cy * s, r * s, p);
    }

    static int ac(int renk, float t) {
        int r = (renk >> 16) & 255, g = (renk >> 8) & 255, b = renk & 255;
        return 0xFF000000 | ((int) (r + (255 - r) * t) << 16) | ((int) (g + (255 - g) * t) << 8) | (int) (b + (255 - b) * t);
    }

    static void gunes(Canvas c, float x, float y, float s, float cx, float cy, float r) {
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        p.setColor(0x1FF5B335);
        c.drawCircle(x + cx * s, y + cy * s, (r + .14f) * s, p);
        p.setColor(GUNES);
        p.setStrokeWidth(Math.max(3, s / 12));
        p.setStrokeCap(Paint.Cap.ROUND);
        for (int i = 0; i < 8; i++) {
            double a = i * Math.PI / 4;
            c.drawLine(x + (float) (cx + Math.cos(a) * (r + .10)) * s, y + (float) (cy + Math.sin(a) * (r + .10)) * s,
                    x + (float) (cx + Math.cos(a) * (r + .24)) * s, y + (float) (cy + Math.sin(a) * (r + .24)) * s, p);
        }
        Paint d = new Paint(Paint.ANTI_ALIAS_FLAG);
        d.setShader(new android.graphics.LinearGradient(0, y + (cy - r) * s, 0, y + (cy + r) * s, 0xFFFFE070, 0xFFF5A623, android.graphics.Shader.TileMode.CLAMP));
        c.drawCircle(x + cx * s, y + cy * s, r * s, d);
    }

    static void bulut(Canvas c, float x, float y, float s, float dx, float dy, int renk) {
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        p.setShader(new android.graphics.LinearGradient(0, y + (.30f + dy) * s, 0, y + (.78f + dy) * s, ac(renk, .45f), renk, android.graphics.Shader.TileMode.CLAMP));
        c.drawCircle(x + (.36f + dx) * s, y + (.58f + dy) * s, .17f * s, p);
        c.drawCircle(x + (.56f + dx) * s, y + (.46f + dy) * s, .22f * s, p);
        c.drawCircle(x + (.74f + dx) * s, y + (.60f + dy) * s, .16f * s, p);
        c.drawRoundRect(new RectF(x + (.24f + dx) * s, y + (.58f + dy) * s, x + (.86f + dx) * s, y + (.76f + dy) * s), .09f * s, .09f * s, p);
    }

    static void ikon(Canvas c, float x, float y, float s, String tur) {
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        p.setStrokeCap(Paint.Cap.ROUND);
        p.setStrokeWidth(Math.max(3, s / 14));
        switch (tur) {
            case "gunes":
                gunes(c, x, y, s, .5f, .5f, .2f);
                break;
            case "az-bulut":
                gunes(c, x, y, s, .4f, .38f, .13f);
                bulut(c, x, y, s, .05f, .02f, BULUT);
                break;
            case "parcali":
                gunes(c, x, y, s, .4f, .4f, .12f);
                bulut(c, x, y, s, .05f, .04f, BULUT);
                break;
            case "yagmur":
                bulut(c, x, y, s, 0, -.12f, BULUT2);
                p.setColor(DAMLA);
                for (float dx : new float[]{.36f, .52f, .68f})
                    c.drawLine(x + dx * s, y + .74f * s, x + (dx - .05f) * s, y + .88f * s, p);
                break;
            case "kar":
                bulut(c, x, y, s, 0, -.12f, BULUT2);
                for (float dx : new float[]{.36f, .52f, .68f}) daire(c, KAR, x, y, s, dx, .82f, .035f);
                break;
            case "firtina":
                bulut(c, x, y, s, 0, -.12f, BULUT2);
                android.graphics.Path yol = new android.graphics.Path();
                yol.moveTo(x + .54f * s, y + .66f * s);
                yol.lineTo(x + .44f * s, y + .82f * s);
                yol.lineTo(x + .53f * s, y + .82f * s);
                yol.lineTo(x + .49f * s, y + .96f * s);
                yol.lineTo(x + .64f * s, y + .76f * s);
                yol.lineTo(x + .55f * s, y + .76f * s);
                yol.close();
                p.setColor(SIMSEK);
                c.drawPath(yol, p);
                break;
            case "sis":
                p.setColor(BULUT);
                float[][] cizgi = {{.2f, .8f}, {.12f, .88f}, {.24f, .76f}, {.16f, .84f}};
                for (int i = 0; i < 4; i++)
                    c.drawLine(x + cizgi[i][0] * s, y + (.3f + i * .14f) * s, x + cizgi[i][1] * s, y + (.3f + i * .14f) * s, p);
                break;
            default:
                bulut(c, x, y, s, 0, -.04f, BULUT);
        }
    }
}
