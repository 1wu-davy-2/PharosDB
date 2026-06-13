import { useTranslation } from "react-i18next";
import "./PlanDiffTable.css";

function fmt(v) {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

export default function PlanDiffTable({ diff }) {
  const { t } = useTranslation();
  if (!diff || diff.length === 0) return null;

  return (
    <div className="qan-detail-section">
      <div className="qan-detail-label">
        {t("qan.plan_diff_title", { count: diff.length })}
      </div>
      <table className="pdt-table">
        <thead>
          <tr>
            <th style={{ width: "26%" }}>{t("qan.plan_diff_path")}</th>
            <th style={{ width: "14%" }}>{t("qan.plan_diff_field")}</th>
            <th style={{ width: "22%" }}>{t("qan.plan_diff_old")}</th>
            <th style={{ width: "22%" }}>{t("qan.plan_diff_new")}</th>
            <th style={{ width: "16%" }}>{t("qan.plan_diff_change")}</th>
          </tr>
        </thead>
        <tbody>
          {diff.map((d, i) => (
            <tr key={i}>
              <td className="pdt-path">{d.path}</td>
              <td>{d.field}</td>
              <td className="pdt-val-a">{fmt(d.a)}</td>
              <td className="pdt-val-b">{fmt(d.b)}</td>
              <td>
                <span className={`pdt-badge pdt-badge--${d.change}`}>
                  {t(`qan.plan_diff_${d.change}`)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
