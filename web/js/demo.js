class DemoMode {
    constructor() {
        this.isActive = false;
        this.timer = null;
        this.tick = 0;
        this.onEvent = () => {};
    }

    getDemoTopology() {
        return {
            nodes: {
                "host-a": { id: "host-a", type: "host", interfaces: [{ip: "192.168.1.10", mac: "aa:bb:cc:01"}] },
                "host-b": { id: "host-b", type: "host", interfaces: [{ip: "192.168.1.20", mac: "aa:bb:cc:02"}] },
                "switch-1": { id: "switch-1", type: "switch" }
            },
            links: {
                "link-1": { id: "link-1", endpoint_a: ["host-a", "eth0"], endpoint_b: ["switch-1", "port0"] },
                "link-2": { id: "link-2", endpoint_a: ["host-b", "eth0"], endpoint_b: ["switch-1", "port1"] }
            }
        };
    }

    start() {
        if (this.isActive) return;
        this.isActive = true;
        this.tick = 0;
        
        const events = [
            { tick: 2, type: 'arp_request', data: { src: "192.168.1.10", target: "192.168.1.20", link_id: "link-1", from: "host-a", to: "switch-1" } },
            { tick: 3, type: 'arp_request', data: { src: "192.168.1.10", target: "192.168.1.20", link_id: "link-2", from: "switch-1", to: "host-b" } },
            { tick: 5, type: 'arp_reply', data: { src: "192.168.1.20", target: "192.168.1.10", link_id: "link-2", from: "host-b", to: "switch-1" } },
            { tick: 6, type: 'arp_reply', data: { src: "192.168.1.20", target: "192.168.1.10", link_id: "link-1", from: "switch-1", to: "host-a" } },
            { tick: 8, type: 'icmp_echo', data: { src: "192.168.1.10", dst: "192.168.1.20", link_id: "link-1", from: "host-a", to: "switch-1" } },
            { tick: 9, type: 'icmp_echo', data: { src: "192.168.1.10", dst: "192.168.1.20", link_id: "link-2", from: "switch-1", to: "host-b" } },
            { tick: 11, type: 'icmp_reply', data: { src: "192.168.1.20", dst: "192.168.1.10", link_id: "link-2", from: "host-b", to: "switch-1" } },
            { tick: 12, type: 'icmp_reply', data: { src: "192.168.1.20", dst: "192.168.1.10", link_id: "link-1", from: "switch-1", to: "host-a" } },
        ];

        this.timer = setInterval(() => {
            this.tick++;
            this.onEvent('simulation_tick', { tick: this.tick });
            
            const currentEvents = events.filter(e => e.tick === this.tick);
            currentEvents.forEach(e => this.onEvent(e.type, e.data));
            
            if (this.tick > 15) {
                this.stop();
            }
        }, 500);
    }

    stop() {
        this.isActive = false;
        clearInterval(this.timer);
    }
}
window.DemoMode = DemoMode;
