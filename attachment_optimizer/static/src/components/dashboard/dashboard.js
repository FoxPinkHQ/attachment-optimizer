/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class StorageDashboard extends Component {
    static template = "attachment_optimizer.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            hasData: false,
            s3Warning: false,
            lastAnalysis: false,
            kpi: {
                total_attachments: 0,
                migrated: 0,
                saved_display: "0 B",
                failed: 0,
            },
            activeOperation: null,
            recentOperations: [],
        });

        onWillStart(async () => {
            await this._loadDashboard();
        });
    }

    async _loadDashboard() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "attachment.storage.mapping",
                "action_get_dashboard_data",
                []
            );
            this.state.hasData = data.total_attachments > 0 || data.recent_operations.length > 0;
            this.state.s3Warning = data.s3_warning || false;
            this.state.lastAnalysis = data.last_analysis || false;
            this.state.kpi = {
                total_attachments: data.total_attachments,
                migrated: data.migrated,
                saved_display: data.saved_display || "0 B",
                failed: data.failed,
            };
            this.state.activeOperation = data.active_operation;
            this.state.recentOperations = (data.recent_operations || []).map((op) => ({
                ...op,
                human_started: this._formatTimestamp(op.started_at) || "—",
                human_duration: op.duration ? this._formatDuration(op.duration) : null,
            }));
        } catch (err) {
            this.notification.add("Unable to load dashboard", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async onAnalyze() {
        try {
            const result = await this.orm.call(
                "attachment.migration.operation",
                "action_analyze_and_queue",
                []
            );
            if (result && result.params) {
                this.action.doAction({
                    type: "ir.actions.client",
                    tag: "display_notification",
                    params: result.params,
                });
            }
            await this._loadDashboard();
        } catch (err) {
            this.notification.add("Analyze failed.", { type: "danger" });
        }
    }

    async onCreateQueue() {
        try {
            const impact = await this.orm.call(
                "attachment.migration.operation",
                "action_get_queue_impact",
                []
            );
            this.action.doAction({
                type: "ir.actions.act_window",
                name: "Confirm Migration Queue",
                res_model: "attachment.migration.queue.confirm",
                view_mode: "form",
                target: "new",
                context: {
                    default_count: impact.count,
                    default_total_size: impact.total_size,
                    default_estimated_duration: impact.estimated_duration,
                    default_candidate_ids: [[6, 0, impact.candidate_ids]],
                },
            });
        } catch (err) {
            this.notification.add("Unable to check queue impact.", { type: "danger" });
        }
    }

    async onRetry(op) {
        try {
            await this.orm.call(
                "attachment.migration.operation",
                "action_retry",
                [[op.id]]
            );
            this.action.doAction({
                type: "ir.actions.client",
                tag: "display_notification",
                params: {
                    title: "Retry",
                    message: "Operation re-queued for retry.",
                    sticky: false,
                },
            });
            await this._loadDashboard();
        } catch (err) {
            this.notification.add("Retry failed.", { type: "danger" });
        }
    }

    onViewFailed() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Failed Operations",
            res_model: "attachment.migration.operation",
            view_mode: "list,form",
            domain: [["state", "=", "failed"]],
        });
    }

    onOpenConfig() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "System Parameters",
            res_model: "ir.config_parameter",
            view_mode: "list",
            domain: [["key", "=ilike", "attachment_storage%"]],
        });
    }

    _formatTimestamp(iso) {
        if (!iso) return null;
        const d = new Date(iso);
        const pad = (n) => String(n).padStart(2, "0");
        return pad(d.getDate()) + " " +
            d.toLocaleString("en", { month: "short" }) + " " +
            pad(d.getHours()) + ":" + pad(d.getMinutes());
    }

    _formatDuration(seconds) {
        if (!seconds || seconds <= 0) return null;
        if (seconds < 60) return seconds + "s";
        if (seconds < 3600) {
            const m = Math.floor(seconds / 60);
            const s = seconds % 60;
            return m + "m " + s + "s";
        }
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        return h + "h " + m + "m";
    }
}

registry
    .category("actions")
    .add("attachment_optimizer.dashboard_action", StorageDashboard);
