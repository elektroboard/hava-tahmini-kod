package tr.havatahmini;

import android.app.Activity;
import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

public class AnaEkran extends Activity {
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        TextView t = new TextView(this);
        t.setText("Hava Tahmini widget'ı yüklendi.\n\nAna ekranda boş bir yere uzun basın, \"Widget'lar\" bölümünden \"Hava Tahmini\"ni ekleyin.\n\nWidget'ın üst şeridine dokununca şehir değişir, başka yerine dokununca yenilenir.");
        t.setTextSize(17);
        t.setPadding(48, 96, 48, 48);
        t.setGravity(Gravity.TOP);
        t.setTextColor(Color.rgb(30, 36, 48));
        final ImageView iv = new ImageView(this);
        iv.setAdjustViewBounds(true);
        LinearLayout k = new LinearLayout(this);
        k.setOrientation(LinearLayout.VERTICAL);
        k.addView(t);
        k.addView(iv);
        setContentView(k);
        final android.content.Context ctx = getApplicationContext();
        new Thread(() -> {
            HavaWidget.indir(ctx);
            final Bitmap bmp = Bitmap.createBitmap(HavaWidget.W, HavaWidget.H, Bitmap.Config.ARGB_8888);
            try {
                HavaWidget.cizBitmap(new Canvas(bmp), ctx);
            } catch (Exception e) {
                HavaWidget.hata(new Canvas(bmp), "Veri okunamadı");
            }
            runOnUiThread(() -> iv.setImageBitmap(bmp));
        }).start();
        Intent i = new Intent(this, HavaWidget.class).setAction(AppWidgetManager.ACTION_APPWIDGET_UPDATE);
        int[] ids = AppWidgetManager.getInstance(this).getAppWidgetIds(new ComponentName(this, HavaWidget.class));
        i.putExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS, ids);
        sendBroadcast(i);
    }
}
