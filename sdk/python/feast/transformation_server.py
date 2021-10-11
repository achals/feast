import sys
from concurrent import futures

import grpc
import pyarrow as pa
from grpc_reflection.v1alpha import reflection

from feast.errors import OnDemandFeatureViewNotFoundException
from feast.feature_store import FeatureStore
from feast.protos.feast.serving.TransformationService_pb2 import (
    DESCRIPTOR,
    TRANSFORMATION_SERVICE_TYPE_PYTHON,
    GetTransformationServiceInfoResponse,
    TransformFeatureResponse,
    ValueType,
)
from feast.protos.feast.serving.TransformationService_pb2_grpc import (
    TransformationServiceServicer,
    add_TransformationServiceServicer_to_server,
)
from feast.version import get_version


class TransformationServer(TransformationServiceServicer):
    def __init__(self, fs: FeatureStore) -> None:
        super().__init__()
        self.fs = fs

    def GetTransformationServiceInfo(self, request, context):
        response = GetTransformationServiceInfoResponse(
            type=TRANSFORMATION_SERVICE_TYPE_PYTHON,
            transformation_service_type_details=f"Python: {sys.version}, Feast: {get_version()}",
        )
        return response

    def TransformFeatures(self, request, context):
        odfv = None
        try:
            odfv = self.fs.get_on_demand_feature_view(request.transformation_name)
        except OnDemandFeatureViewNotFoundException:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            raise

        assert odfv

        df = pa.ipc.open_file(request.transformation_input.arrow_value).read_pandas()

        result_df = odfv.get_transformed_features_df(True, df)
        result_arrow = pa.Table.from_pandas(result_df)
        sink = pa.BufferOutputStream()
        writer = pa.ipc.new_file(sink, result_arrow.schema)
        writer.write_batch(result_arrow)
        writer.close()

        buf = sink.getvalue()

        return TransformFeatureResponse(
            transformation_output=ValueType(arrow_value=buf)
        )


def start_server(store: FeatureStore, port: int):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    add_TransformationServiceServicer_to_server(TransformationServer(store), server)
    service_names_available_for_reflection = (
        DESCRIPTOR.services_by_name["TransformationService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names_available_for_reflection, server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    server.wait_for_termination()
