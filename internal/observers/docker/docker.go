// Package docker is an observer that watches a docker daemon and reports
// container ports as service endpoints.
package docker

import (
	"strconv"

	"github.com/pkg/errors"
	log "github.com/sirupsen/logrus"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/client"
	"golang.org/x/net/context"

	"github.com/signalfx/signalfx-agent/internal/core/config"
	"github.com/signalfx/signalfx-agent/internal/core/services"
	"github.com/signalfx/signalfx-agent/internal/observers"
)

const (
	observerType     = "docker"
	dockerAPIVersion = "v1.22"
)

// OBSERVER(docker): Queries the Docker Engine API for running containers.  If
// you are using Kubernetes, you should use the [k8s-api
// observer](./k8s-api.md) instead of this.
//
// Note that you will need permissions to access the Docker engine API.  For a
// Docker domain socket URL, this means that the agent needs to have read
// permissions on the socket.  We don't currently support authentication for
// HTTP URLs.

// ENDPOINT_TYPE(ContainerEndpoint): true

var logger = log.WithFields(log.Fields{"observerType": observerType})

// Docker observer plugin
type Docker struct {
	client           *client.Client
	serviceCallbacks *observers.ServiceCallbacks
	serviceDiffer    *observers.ServiceDiffer
	config           *Config
}

// Config specific to the Docker observer
type Config struct {
	config.ObserverConfig
	DockerURL string `yaml:"dockerURL" default:"unix:///var/run/docker.sock"`
	// How often to poll the docker API
	PollIntervalSeconds int `yaml:"pollIntervalSeconds" default:"10"`
}

// Validate the docker-specific config
func (c *Config) Validate() error {
	if c.PollIntervalSeconds < 1 {
		return errors.New("pollIntervalSeconds must be greater than 0")
	}
	return nil
}

func init() {
	observers.Register(observerType, func(cbs *observers.ServiceCallbacks) interface{} {
		return &Docker{
			serviceCallbacks: cbs,
		}
	}, &Config{})
}

// Configure the docker client
func (docker *Docker) Configure(config *Config) error {
	defaultHeaders := map[string]string{"User-Agent": "signalfx-agent"}

	var err error
	docker.client, err = client.NewClient(config.DockerURL, dockerAPIVersion, nil, defaultHeaders)
	if err != nil {
		return errors.Wrapf(err, "Could not create docker client")
	}

	if docker.serviceDiffer != nil {
		docker.serviceDiffer.Stop()
	}

	docker.serviceDiffer = &observers.ServiceDiffer{
		DiscoveryFn:     docker.discover,
		IntervalSeconds: config.PollIntervalSeconds,
		Callbacks:       docker.serviceCallbacks,
	}
	docker.config = config

	docker.serviceDiffer.Start()

	return nil
}

// Discover services by querying docker api
func (docker *Docker) discover() []services.Endpoint {
	options := types.ContainerListOptions{All: true}
	containers, err := docker.client.ContainerList(context.Background(), options)
	if err != nil {
		logger.WithFields(log.Fields{
			"options":   options,
			"dockerURL": docker.config.DockerURL,
			"error":     err,
		}).Error("Could not get container list from docker")
		return nil
	}

	instances := make([]services.Endpoint, 0)

	for _, c := range containers {
		if c.State == "running" {
			serviceContainer := &services.Container{
				ID:      c.ID,
				Names:   c.Names,
				Image:   c.Image,
				Command: c.Command,
				State:   c.State,
				Labels:  c.Labels,
			}

			for _, port := range c.Ports {
				id := serviceContainer.PrimaryName() + "-" + c.ID[:12] + "-" + strconv.Itoa(int(port.PrivatePort))

				endpoint := services.NewEndpointCore(id, "", observerType)
				// Use the IP Address of the first network we iterate over.
				// This can be made configurable if so desired.
				for _, n := range c.NetworkSettings.Networks {
					endpoint.Host = n.IPAddress
					break
				}
				endpoint.PortType = services.PortType(port.Type)
				endpoint.Port = uint16(port.PrivatePort)

				orchestration := services.NewOrchestration("docker", services.DOCKER, nil, services.PRIVATE)

				si := &services.ContainerEndpoint{
					EndpointCore:  *endpoint,
					AltPort:       uint16(port.PublicPort),
					Container:     *serviceContainer,
					Orchestration: *orchestration,
				}

				instances = append(instances, si)
			}
		}
	}

	return instances
}

// Shutdown the service differ routine
func (docker *Docker) Shutdown() {
	if docker.serviceDiffer != nil {
		docker.serviceDiffer.Stop()
	}
}
