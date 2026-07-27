/** @odoo-module **/

import { Component, useState, onWillStart, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

export class StorageDashboard extends Component {
    static template = "attachment_optimizer.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this._pollTimer = null;
        this._pollInFlight = false;
        this._loadSeq = 0;

        this.state = useState({
            loadingDashboard: false,
            analyzing: false,
            processingQueue: false,
            refreshing: false,
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
            opTotal: 0,
            pollActive: false,
        });

        onWillStart(async () => {
            await this._loadDashboard();
        });

        onWillUnmount(() => {
            this._stopPolling();
        });
    }

    async _loadDashboard() {
        const seq = ++this._loadSeq;
        this.state.loadingDashboard = true;
        try {
            const data = await this.orm.call(
                "attachment.storage.mapping",
                "action_get_dashboard_data",
                []
            );
            if (seq !== this._loadSeq) return;
            this.state.hasData = data.total_attachments > 0;
            this.state.s3Warning = data.s3_warning || false;
            this.state.lastAnalysis = data.last_analysis || false;
            this.state.kpi = {
                total_attachments: data.total_attachments,
                migrated: data.migrated,
                saved_display: data.saved_display || "0 B",
                failed: data.failed,
            };
            this.state.activeOperation = data.active_operation;
            this.state.recentOperations = data.recent_operations || [];
            this.state.opTotal = data.recent_total || 0;
            this._handlePolling(data.active_operation);
        } catch (err) {
            if (seq === this._loadSeq) {
                this.notification.add("Unable to load dashboard", { type: "danger" });
            }
        } finally {
            if (seq === this._loadSeq) {
                this.state.loadingDashboard = false;
            }
        }
    }

    _handlePolling(activeOp) {
        if (activeOp) {
            this._startPolling();
        } else {
            this._stopPolling();
        }
    }

    _startPolling() {
        if (this._pollTimer || this._pollInFlight) return;
        this.state.pollActive = true;
        const poll = async () => {
            if (this._pollInFlight) return;
            this._pollInFlight = true;
            try {
                const data = await this.orm.call(
                    "attachment.storage.mapping",
                    "action_get_dashboard_data",
                    []
                );
                if (!this._pollTimer) return;
                this.state.kpi = {
                    total_attachments: data.total_attachments,
                    migrated: data.migrated,
                    saved_display: data.saved_display || "0 B",
                    failed: data.failed,
                };
                this.state.activeOperation = data.active_operation;
                this.state.recentOperations = data.recent_operations || [];
                this.state.opTotal = data.recent_total || 0;
                if (!data.active_operation) {
                    this._stopPolling();
                }
                if (this._pollTimer) {
                    this._pollTimer = setTimeout(poll, 3000);
                }
            } catch {
                if (this._pollTimer) {
                    this._pollTimer = setTimeout(poll, 5000);
                }
            } finally {
                this._pollInFlight = false;
            }
        };
        this._pollTimer = setTimeout(poll, 3000);
    }

    _stopPolling() {
        if (this._pollTimer) {
            clearTimeout(this._pollTimer);
            this._pollTimer = null;
        }
        this._pollInFlight = false;
        this.state.pollActive = false;
    }

    async onAnalyze() {
        this.state.analyzing = true;
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
        } finally {
            this.state.analyzing = false;
        }
    }

    async onProcessQueue() {
        this.state.processingQueue = true;
        try {
            const result = await this.orm.call(
                "attachment.migration.operation",
                "action_process_queue",
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
            this.notification.add("Process failed.", { type: "danger" });
        } finally {
            this.state.processingQueue = false;
        }
    }

    async onCreateQueue() {
        try {
            const impact = await this.orm.call(
                "attachment.migration.operation",
                "action_get_queue_impact",
                []
            );
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Confirm Migration Queue",
                res_model: "attachment.migration.queue.confirm",
                views: [[false, "form"]],
                view_mode: "form",
                target: "new",
                context: {
                    default_count: impact.count,
                    default_total_size: impact.total_size,
                    default_estimated_duration: impact.estimated_duration,
                    default_candidate_ids: [[6, 0, impact.candidate_ids]],
                },
            }, {
                onClose: async () => {
                    await this._loadDashboard();
                },
            });
        } catch (err) {
            this.notification.add("Unable to check queue impact.", { type: "danger" });
        }
    }

    async _retryAllFailed() {
        const failedCount = this.state.kpi.failed;
        if (failedCount === 0) {
            this.notification.add("No failed operations to retry.", { type: "info" });
            return;
        }
        try {
            const result = await this.orm.call(
                "attachment.migration.operation",
                "action_retry_all_failed",
                []
            );
            if (result && result.params) {
                this.action.doAction({
                    type: "ir.actions.client",
                    tag: "display_notification",
                    params: result.params,
                });
            } else {
                this.notification.add("Queued " + failedCount + " failed operation(s) for retry.", { type: "success" });
            }
            await this._loadDashboard();
        } catch (err) {
            this.notification.add("Retry all failed.", { type: "danger" });
        }
    }

    onRetryAllFailed() {
        this.dialog.add(ConfirmationDialog, {
            body: "Retry all failed operations?",
            confirm: () => this._retryAllFailed(),
            confirmLabel: "Retry All",
            cancelLabel: "Cancel",
        });
    }

    onViewFailed() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Failed Operations",
            res_model: "attachment.migration.operation",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "=", "failed"]],
        });
    }

    onViewAllOperations() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Migration Operations",
            res_model: "attachment.migration.operation",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
        });
    }

    async onRefresh() {
        this.state.refreshing = true;
        await this._loadDashboard();
        this.state.refreshing = false;
    }

    onOpenConfig() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "System Parameters",
            res_model: "ir.config_parameter",
            view_mode: "list",
            views: [[false, "list"]],
            domain: [["key", "=ilike", "attachment_storage%"]],
        });
    }

}

registry
    .category("actions")
    .add("attachment_optimizer.dashboard_action", StorageDashboard);
