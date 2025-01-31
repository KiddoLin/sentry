from sentry.api.serializers import Serializer, register
from sentry.models.eventattachment import EventAttachment
from sentry.models.files.file import File


@register(EventAttachment)
class EventAttachmentSerializer(Serializer):
    def get_attrs(self, item_list, user, **kwargs):
        files = {f.id: f for f in File.objects.filter(id__in=[ea.file_id for ea in item_list])}
        return {ea: {"file": files[ea.file_id]} for ea in item_list}

    def serialize(self, obj, attrs, user):
        file = attrs["file"]
        return {
            "id": str(obj.id),
            "name": obj.name,
            "headers": file.headers,
            "mimetype": obj.mimetype,
            "size": file.size,
            "sha1": file.checksum,
            "dateCreated": file.timestamp,
            "type": obj.type,
            "event_id": obj.event_id,
        }
