import { patch } from "@web/core/utils/patch";
import { ReportAction } from "@web/webclient/actions/reports/report_action";

/**
 * Period report drill-down: amounts marked with .np-drill open the journal
 * items behind them (see np.period.report.action_drilldown).
 */
patch(ReportAction.prototype, {
    onIframeLoaded(ev) {
        super.onIframeLoaded(...arguments);
        const doc = ev.target.contentWindow.document;
        for (const page of doc.querySelectorAll("[data-np-report-id]")) {
            const reportId = Number(page.dataset.npReportId);
            for (const el of page.querySelectorAll(".np-drill[data-np-kind]")) {
                el.addEventListener("click", async () => {
                    const action = await this.env.services.orm.call(
                        "np.period.report",
                        "action_drilldown",
                        [[reportId], el.dataset.npKind],
                        {
                            account_id: el.dataset.npAccount ? Number(el.dataset.npAccount) : null,
                            section: el.dataset.npSection || null,
                        }
                    );
                    this.action.doAction(action);
                });
            }
        }
    },
});
