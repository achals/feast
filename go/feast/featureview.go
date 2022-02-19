package feast

import (
	"github.com/feast-dev/feast/go/protos/feast/core"
	"github.com/feast-dev/feast/go/protos/feast/types"
	durationpb "google.golang.org/protobuf/types/known/durationpb"
)

const (
	DUMMY_ENTITY_ID = "__dummy_id"
	DUMMY_ENTITY_NAME = "__dummy"
	DUMMY_ENTITY_VAL = ""
)

var DUMMY_ENTITY types.Value = types.Value{Val: &types.Value_StringVal{StringVal: DUMMY_ENTITY_VAL} }

// Wrapper around core.FeatureView to add projection
type FeatureView struct {
	base *BaseFeatureView
	ttl *durationpb.Duration
	// entities []string
	// make entities set so that search for dummy entity is faster
	entities map[string]bool
}

func NewFeatureViewFromProto(proto *core.FeatureView) *FeatureView {
	featureView := &FeatureView{	base: NewBaseFeatureView(	proto.Spec.Name, proto.Spec.Features),
									ttl: &(*proto.Spec.Ttl),
									// entities: proto.Spec.Entities,
								}
	if len(proto.Spec.Entities) == 0 {
		featureView.entities = map[string]bool{DUMMY_ENTITY_NAME:true}
	} else {
		featureView.entities = make(map[string]bool)
		for _, entityName := range proto.Spec.Entities {
			featureView.entities[entityName] = true
		}
	}
	return featureView
}

func (fs *FeatureView) NewFeatureViewFromBase(base *BaseFeatureView) *FeatureView {
	ttl := *fs.ttl
	featureView := &FeatureView{	base: base,
									ttl: &ttl,
									entities: fs.entities,
								}
	return featureView
}

