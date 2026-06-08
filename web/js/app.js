class NetSimApp {
    constructor() {
        this.ws = null;
        this.topologyRenderer = null;
        this.packetAnimator = null;
        this.panelManager = null;
        this.demoMode = null;
    }

    async init() {
        console.log("NetSim App Initializing...");

        // 1. Initialize UI panels
        this.panelManager = new window.PanelManager();
        
        // 2. Initialize Topology
        this.topologyRenderer = new window.TopologyRenderer('topology-container');
        this.topologyRenderer.onNodeSelected = (node) => this.panelManager.showNodeDetail(node);
        
        // 3. Initialize Packet Animator
        this.packetAnimator = new window.PacketAnimator(this.topologyRenderer);

        // 4. Setup Command Input
        this.panelManager.setupCommandInput((cmd) => this.handleCommand(cmd));
        
        // 5. Setup Controls
        document.getElementById('btn-play').addEventListener('click', () => this.ws ? this.ws.send('start') : this.demoMode.start());
        document.getElementById('btn-pause').addEventListener('click', () => this.ws ? this.ws.send('stop') : this.demoMode.stop());
        document.getElementById('btn-step').addEventListener('click', () => this.ws ? this.ws.send('step') : null);
        document.getElementById('btn-reset').addEventListener('click', () => {
            if (this.ws) {
                this.ws.send('reset');
            } else {
                this.demoMode.stop();
                this.topologyRenderer.clear();
                this.panelManager.clearLog();
            }
        });

        // Try connecting to WebSocket
        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            this.ws = new window.SimWebSocket(`${protocol}//${window.location.host}/ws`);
            this.ws.onEvent('topology_snapshot', (payload) => {
                this.topologyRenderer.loadTopology(payload);
                this.panelManager.setSimulationState('stopped');
            });
            this.ws.onEvent('simulation_tick', (payload) => {
                this.panelManager.updateStats({ tick: payload.tick });
            });
            this.ws.onEvent('simulation_start', () => this.panelManager.setSimulationState('playing'));
            this.ws.onEvent('simulation_stop', () => this.panelManager.setSimulationState('stopped'));
            
            const handlePacketEvent = (eventType, payload) => {
                this.panelManager.addLogEntry(eventType, payload);
                this.packetAnimator.handleEvent(eventType, payload);
            };
            
            ['packet_sent', 'packet_received', 'packet_dropped', 'arp_request', 'arp_reply', 'icmp_echo', 'icmp_reply'].forEach(event => {
                this.ws.onEvent(event, (payload) => handlePacketEvent(event, payload));
            });

            await this.ws.connect();
            console.log("Connected to Live Simulation Server");
        } catch (e) {
            console.warn("WebSocket failed, falling back to Demo Mode", e);
            this.ws = null;
            this.startDemoMode();
        }
    }

    startDemoMode() {
        this.demoMode = new window.DemoMode();
        this.topologyRenderer.loadTopology(this.demoMode.getDemoTopology());
        
        this.demoMode.onEvent = (type, data) => {
            this.panelManager.addLogEntry(type, data);
            this.packetAnimator.handleEvent(type, data);
            if (type === 'simulation_tick') {
                this.panelManager.updateStats({ tick: data.tick });
            }
        };
        
        document.getElementById('conn-status').classList.add('demo');
        document.getElementById('conn-status').title = "Demo Mode (Offline)";
    }

    handleCommand(cmdStr) {
        if (!cmdStr.trim()) return;
        this.panelManager.addCommandResponse(`> ${cmdStr}`);
        
        const parts = cmdStr.trim().split(/\s+/);
        const cmd = parts[0].toLowerCase();
        
        if (!this.ws) {
            this.panelManager.addCommandResponse("Error: Commands require active server connection");
            return;
        }

        if (cmd === 'ping') {
            if (parts.length < 3) {
                this.panelManager.addCommandResponse("Usage: ping <source_node> <target_ip>");
                return;
            }
            this.ws.send('ping', { from: parts[1], to: parts[2] });
            this.panelManager.addCommandResponse("Ping injected.");
        } else {
            this.panelManager.addCommandResponse(`Unknown command: ${cmd}`);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.app = new NetSimApp();
    window.app.init();
});
