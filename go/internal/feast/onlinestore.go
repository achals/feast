package feast

import (
	"errors"
	"fmt"
	"github.com/feast-dev/feast/go/internal/config"
	"github.com/feast-dev/feast/go/protos/feast/serving"
	"github.com/feast-dev/feast/go/protos/feast/types"
	"github.com/golang/protobuf/ptypes/timestamp"
)

type FeatureData struct {
	reference serving.FeatureReferenceV2
	timestamp timestamp.Timestamp
	value     types.Value
}

type OnlineStore interface {
	// OnlineRead reads multiple features (specified in featureReferences) for multiple
	// entity keys (specified in entityKeys) and returns an array of array of features,
	// where each feature contains 3 fields:
	//   1. feature Reference
	//   2. feature event timestamp
	//   3. feature value
	// The inner array will have the same size as featureReferences,
	// while the outer array will have the same size as entityKeys.

	// TODO (Ly): Can we return [][]FeatureData, []timstamps, error
	// instead and remove timestamp from FeatureData struct to mimic Python's code
	// and reduces repeated memory storage for the same timstamp (which is stored as value and not as a pointer).
	// Should each attribute in FeatureData be stored as a pointer instead since the current
	// design forces value copied in OnlineRead + GetOnlineFeatures
	// (array is destructed so we cannot use the same fields in each
	// Feature object as pointers in GetOnlineFeaturesResponse)
	// => allocate memory for each field once in OnlineRead
	// and reuse them in GetOnlineFeaturesResponse?
	OnlineRead(entityKeys []types.EntityKey, view string, features []string) ([][]FeatureData, error)
	// Destruct must be call once user is done using OnlineStore
	// This is to comply with the Connector since we have to close the plugin
	Destruct()
}

func getOnlineStoreType(onlineStoreConfig map[string]interface{}) (string, bool) {
	if onlineStoreType, ok := onlineStoreConfig["type"]; !ok {
		return "", false
	} else {
		result, ok := onlineStoreType.(string)
		return result, ok
	}
}

func getOnlineStore(config *config.RepoConfig) (OnlineStore, error) {
	onlineStoreType, ok := getOnlineStoreType(config.OnlineStore)
	if !ok {
		return nil, errors.New(fmt.Sprintf("could not get online store type from online store config: %+v", config.OnlineStore))
	}
	if onlineStoreType == "redis" {
		onlineStore, err := NewRedisOnlineStore(config.Project, config.OnlineStore)
		return onlineStore, err
	} else {
		return nil, errors.New("only Redis is supported as an online store for now")
	}
}
