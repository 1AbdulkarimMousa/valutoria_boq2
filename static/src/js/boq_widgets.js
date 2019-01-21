/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";

// BOQ Progress Bar Widget
class BoqProgressBar extends Component {
    static template = "boq.ProgressBar";
    
    get progressStyle() {
        return `width: ${this.props.record.data[this.props.name] || 0}%`;
    }
    
    get progressClass() {
        const value = this.props.record.data[this.props.name] || 0;
        if (value < 25) return "bg-danger";
        if (value < 50) return "bg-warning";
        if (value < 75) return "bg-info";
        return "bg-success";
    }
}

// BOQ Status Badge Widget  
class BoqStatusBadge extends Component {
    static template = "boq.StatusBadge";
    
    get statusClass() {
        const status = this.props.record.data[this.props.name];
        const statusMap = {
            'draft': 'badge-secondary',
            'submitted': 'badge-warning', 
            'approved': 'badge-success',
            'in_progress': 'badge-primary',
            'done': 'badge-info',
            'cancelled': 'badge-dark'
        };
        return statusMap[status] || 'badge-light';
    }
}

// Register widgets
registry.category("fields").add("boq_progress_bar", BoqProgressBar);
registry.category("fields").add("boq_status_badge", BoqStatusBadge);

// BOQ utility functions
window.BoqUtils = {
    formatCurrency: function(amount, currency) {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: currency || 'USD'
        }).format(amount);
    },
    
    calculateProgress: function(current, total) {
        return total ? Math.round((current / total) * 100) : 0;
    },
    
    validateQuantity: function(current, previous, master) {
        return (current + previous) <= master;
    }
};

// Initialize BOQ specific behaviors when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('BOQ Module JavaScript loaded');
});