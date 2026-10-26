import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from typing import Dict, Optional

CHART_COLORS = [
    "#4C6EF5",
    "#15AABF",
    "#40C057",
    "#FAB005",
    "#FA5252",
    "#BE4BDB",
    "#FD7E14",
    "#22B8CF",
    "#7950F2",
    "#82C91E",
    "#868E96",
]

class ChartService:
    def __init__(self):
        plt.rcParams['font.sans-serif'] = ['Segoe UI', 'Arial', 'DejaVu Sans', 'Helvetica', 'sans-serif']
        plt.rcParams['axes.unicode_minus'] = False

    def generate_expense_pie_chart(self, expense_by_category: Dict[str, int], month: int, year: int) -> Optional[io.BytesIO]:
        """
        Vẽ biểu đồ tròn (Pie Chart) phân bổ chi tiêu theo danh mục.
        Trả về BytesIO chứa ảnh PNG.
        """
        if not expense_by_category:
            return None

        labels = list(expense_by_category.keys())
        values = list(expense_by_category.values())
        total = sum(values)

        if total == 0:
            return None

        fig, ax = plt.subplots(figsize=(8, 6), dpi=120)
        fig.patch.set_facecolor('#FFFFFF')
        ax.set_facecolor('#FFFFFF')

        colors = CHART_COLORS[:len(labels)] if len(labels) <= len(CHART_COLORS) else None

        def autopct_format(pct):
            val = int(round(pct * total / 100.0))
            if pct < 4:
                return f"{pct:.1f}%"
            if val >= 1_000_000:
                val_str = f"{val/1_000_000:.1f}tr"
            elif val >= 1_000:
                val_str = f"{val/1_000:.0f}k"
            else:
                val_str = f"{val:,}đ"
            return f"{pct:.1f}%\n({val_str})"

        wedges, texts, autotexts = ax.pie(
            values,
            labels=labels,
            autopct=autopct_format,
            pctdistance=0.75,
            startangle=140,
            colors=colors,
            textprops=dict(color="#1A1A1A", fontsize=10, weight='medium'),
            wedgeprops=dict(width=0.45, edgecolor='#FFFFFF', linewidth=2)
        )

        for autotext in autotexts:
            autotext.set_color('#2B2B2B')
            autotext.set_fontsize(9)
            autotext.set_weight('bold')

        if total >= 1_000_000:
            total_display = f"{total/1_000_000:.2f} triệu"
        else:
            total_display = f"{total:,.0f} đ"

        ax.text(
            0, 0,
            f"TỔNG CHI\n{total_display}",
            ha='center', va='center',
            fontsize=12, weight='bold',
            color='#1E293B'
        )

        plt.title(f"Phân Bổ Chi Tiêu - Tháng {month:02d}/{year}", fontsize=14, weight='bold', pad=20, color='#0F172A')
        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        img_buffer.seek(0)
        return img_buffer

chart_service = ChartService()
