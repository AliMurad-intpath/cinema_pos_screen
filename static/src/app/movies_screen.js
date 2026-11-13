import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";

const REFRESH_MS = 10000;

function addDays(iso, n) {
    const d = new Date(iso + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
}

export class MoviesScreen extends Component {
    static template = "cinema_pos_screen.MoviesScreen";
    static props = ["*"];

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            busy: false,
            date: null,
            dates: [],
            data: null,
            movie: null,
            showtime: null,
            seatmap: null,
            selected: [],
        });
        onWillStart(() => this.loadDay(null));
        this._timer = setInterval(() => this.refreshSeatmap(), REFRESH_MS);
        onWillUnmount(() => clearInterval(this._timer));
    }

    // ------------------------------------------------------------ helpers
    errorMessage(error) {
        return error?.data?.message || error?.message || String(error);
    }

    notify(message, type = "danger") {
        this.notification.add(message, { type });
    }

    formatPrice(value) {
        const format = this.env.utils?.formatCurrency;
        return format ? format(value) : Number(value).toFixed(2);
    }

    dateLabel(iso) {
        if (iso === this.state.data?.today) {
            return "Today";
        }
        const d = new Date(iso + "T00:00:00Z");
        return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", timeZone: "UTC" });
    }

    posterUrl(movie) {
        return `/web/image/cinema.movie/${movie.id}/poster_256`;
    }

    // -------------------------------------------------------------- data
    async loadDay(date) {
        this.state.loading = true;
        try {
            const data = await this.orm.call("cinema.booking", "pos_get_screen_data", [], {
                config_id: this.pos.config.id,
                date,
            });
            this.state.data = data;
            this.state.date = data.date;
            this.state.dates = Array.from({ length: 7 }, (_, i) => addDays(data.today, i));
            this.state.movie = null;
            this.state.showtime = null;
            this.state.seatmap = null;
            this.state.selected = [];
        } catch (error) {
            this.notify(this.errorMessage(error));
        } finally {
            this.state.loading = false;
        }
    }

    async selectDate(date) {
        if (date !== this.state.date) {
            await this.loadDay(date);
        }
    }

    selectMovie(movie) {
        this.state.movie = movie;
        this.state.showtime = null;
        this.state.seatmap = null;
        this.state.selected = [];
    }

    async selectShowtime(showtime) {
        if (showtime.availability === "sold_out") {
            return;
        }
        this.state.showtime = showtime;
        this.state.selected = [];
        this.state.seatmap = null;
        await this.loadSeatmap();
    }

    async loadSeatmap() {
        try {
            this.state.seatmap = await this.orm.call("cinema.booking", "pos_get_seatmap", [], {
                showtime_id: this.state.showtime.id,
            });
        } catch (error) {
            this.notify(this.errorMessage(error));
        }
    }

    async refreshSeatmap() {
        if (!this.state.showtime || this.state.busy) {
            return;
        }
        try {
            const seatmap = await this.orm.call("cinema.booking", "pos_get_seatmap", [], {
                showtime_id: this.state.showtime.id,
            });
            this.state.seatmap = seatmap;
            const free = new Set(seatmap.seats.filter((s) => s.status === "free").map((s) => s.id));
            const lost = this.state.selected.filter((s) => !free.has(s.seat_id));
            if (lost.length) {
                this.state.selected = this.state.selected.filter((s) => free.has(s.seat_id));
                this.notify(
                    `Seat ${lost.map((s) => s.label).join(", ")} was just taken by another sale.`,
                    "warning"
                );
            }
        } catch {
            // A failed background refresh is not worth interrupting the cashier.
        }
    }

    // -------------------------------------------------------------- seats
    get seatRows() {
        const seatmap = this.state.seatmap;
        if (!seatmap) {
            return [];
        }
        const rows = new Map();
        for (const seat of seatmap.seats) {
            if (!rows.has(seat.row)) {
                rows.set(seat.row, []);
            }
            rows.get(seat.row).push(seat);
        }
        return [...rows].map(([label, seats]) => {
            seats.sort((a, b) => a.number - b.number);
            let prev = null;
            const withGaps = seats.map((seat) => {
                const gap = prev !== null && seat.x - prev.x > 0.8;
                prev = seat;
                return { ...seat, gap };
            });
            return { label, seats: withGaps };
        });
    }

    isSelected(seat) {
        return this.state.selected.some((s) => s.seat_id === seat.id);
    }

    get defaultTicketTypeId() {
        const types = this.state.data.ticket_types;
        return (types.find((t) => t.code === "standard") || types[0])?.id;
    }

    toggleSeat(seat) {
        if (seat.status !== "free") {
            return;
        }
        const index = this.state.selected.findIndex((s) => s.seat_id === seat.id);
        if (index >= 0) {
            this.state.selected.splice(index, 1);
        } else {
            this.state.selected.push({
                seat_id: seat.id,
                label: seat.label,
                type: seat.type,
                base_price: seat.price,
                ticket_type_id: this.defaultTicketTypeId,
            });
        }
    }

    setTicketType(selection, value) {
        selection.ticket_type_id = parseInt(value, 10);
    }

    typeFactor(id) {
        return this.state.data.ticket_types.find((t) => t.id === id)?.price_factor ?? 1;
    }

    priceOf(selection) {
        return selection.base_price * this.typeFactor(selection.ticket_type_id);
    }

    get total() {
        return this.state.selected.reduce((sum, s) => sum + this.priceOf(s), 0);
    }

    // -------------------------------------------------------------- order
    get currentOrder() {
        return this.pos.getOrder() || this.pos.addNewOrder();
    }

    goBack() {
        this.pos.navigate("ProductScreen", { orderUuid: this.currentOrder.uuid });
    }

    async addToOrder() {
        if (!this.state.selected.length || this.state.busy) {
            return;
        }
        this.state.busy = true;
        let booking = null;
        try {
            booking = await this.orm.call("cinema.booking", "pos_hold", [], {
                showtime_id: this.state.showtime.id,
                seats: this.state.selected.map((s) => ({
                    seat_id: s.seat_id,
                    ticket_type_id: s.ticket_type_id,
                })),
                config_id: this.pos.config.id,
            });
            const order = this.currentOrder;
            for (const ticket of booking.tickets) {
                const template = this.pos.models["product.template"].get(ticket.product_tmpl_id);
                if (!template) {
                    throw new Error(
                        "The 'Cinema Ticket' product is not loaded in this POS. " +
                            "Make sure it is available in Point of Sale."
                    );
                }
                const line = await this.pos.addLineToCurrentOrder(
                    {
                        product_tmpl_id: template,
                        qty: 1,
                        price_unit: ticket.price,
                        cinema_booking_ref: booking.booking_id,
                        cinema_line_ref: ticket.line_id,
                    },
                    {},
                    false
                );
                if (!line) {
                    throw new Error("The ticket line could not be added to the order.");
                }
                if (typeof line.setUnitPrice === "function") {
                    line.setUnitPrice(ticket.price);
                }
                const note = `${booking.label} · Seat ${ticket.seat} (${ticket.ticket_type})`;
                if (typeof line.setCustomerNote === "function") {
                    line.setCustomerNote(note);
                }
            }
            this.pos.navigate("ProductScreen", { orderUuid: order.uuid });
        } catch (error) {
            if (booking) {
                // Do not leave seats blocked if the order could not be built.
                this.orm.call("cinema.booking", "pos_release", [], { booking_id: booking.booking_id });
            }
            this.notify(this.errorMessage(error));
            await this.refreshSeatmap();
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("pos_pages").add("MoviesScreen", {
    name: "MoviesScreen",
    component: MoviesScreen,
    route: `/pos/ui/${odoo.pos_config_id}/movies`,
    params: {},
});
