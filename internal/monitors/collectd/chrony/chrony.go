// +build !windows

package chrony

//go:generate collectd-template-to-go chrony.tmpl

import (
	"github.com/signalfx/signalfx-agent/internal/core/config"
	"github.com/signalfx/signalfx-agent/internal/monitors"
	"github.com/signalfx/signalfx-agent/internal/monitors/collectd"
)

const monitorType = "collectd/chrony"

// MONITOR(collectd/chrony): Collectd NTP data from a chronyd instance
//
// See https://collectd.org/documentation/manpages/collectd.conf.5.shtml#plugin_chrony

func init() {
	monitors.Register(monitorType, func() interface{} {
		return &Monitor{
			MonitorCore: *collectd.NewMonitorCore(CollectdTemplate),
		}
	}, &Config{})
}

// Config is the monitor-specific config with the generic config embedded
type Config struct {
	// This cannot be multi instance until there is a way to differentiate them
	// in collectd
	config.MonitorConfig `singleInstance:"true"`

	// The hostname of the chronyd instance
	Host string `yaml:"host" validate:"required" default:"localhost"`
	// The UDP port number of the chronyd instance.  Defaults to 323 in
	// collectd if unspecified.
	Port *uint16 `yaml:"port"`
	// How long to wait for a response from chronyd before considering it down.
	// Defaults to 2 seconds in the collectd plugin if not specified
	Timeout *uint `yaml:"timeout"`
}

// Monitor is the main type that represents the monitor
type Monitor struct {
	collectd.MonitorCore
}

// Configure configures and runs the plugin in collectd
func (m *Monitor) Configure(conf *Config) error {
	return m.SetConfigurationAndRun(conf)
}
