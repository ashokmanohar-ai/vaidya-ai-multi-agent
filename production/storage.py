"""Private S3 storage; never return public URLs for clinical artifacts."""
from __future__ import annotations
from io import BytesIO
import re

OBJECT_KEY = re.compile(r'^hospital/[0-9a-f-]{36}/jobs/[0-9a-f-]{36}/[a-z0-9-]{1,100}\.(?:txt|json|docx|png|jpg|wav|mp3|webm|m4a|ogg)$')

class PrivateS3:
    def __init__(self, bucket: str, region: str, kms_key: str, client=None):
        if not bucket: raise ValueError('Private bucket required')
        if client is None:
            import boto3
            client=boto3.client('s3',region_name=region)
        self.client=client
        self.bucket=bucket
        self.kms_key=kms_key

    @staticmethod
    def validate_key(key):
        if not OBJECT_KEY.fullmatch(key): raise ValueError('Invalid private object key')
        return key

    def put(self, key: str, content: bytes, mime: str):
        self.validate_key(key)
        if len(content)>25*1024*1024:raise ValueError('Object too large')
        args=dict(Bucket=self.bucket,Key=key,Body=content,ContentType=mime,
                  ServerSideEncryption='aws:kms' if self.kms_key else 'AES256')
        if self.kms_key:args['SSEKMSKeyId']=self.kms_key
        self.client.put_object(**args)

    def get(self, key: str, max_bytes=25*1024*1024) -> bytes:
        self.validate_key(key)
        result=self.client.get_object(Bucket=self.bucket,Key=key)
        raw=result['Body'].read(max_bytes+1)
        if len(raw)>max_bytes:raise ValueError('Object limit exceeded')
        return raw

    def presign_upload(self,key,mime,expires=300):
        self.validate_key(key)
        if mime not in ('audio/wav','audio/mpeg','audio/webm','audio/mp4','audio/ogg','image/png','image/jpeg'):
            raise ValueError('Unsupported upload type')
        fields={'Content-Type':mime,'x-amz-server-side-encryption':'aws:kms' if self.kms_key else 'AES256'}
        if self.kms_key: fields['x-amz-server-side-encryption-aws-kms-key-id']=self.kms_key
        conditions=[['content-length-range',1,25*1024*1024],{'Content-Type':mime},
                    {'x-amz-server-side-encryption':fields['x-amz-server-side-encryption']}]
        if self.kms_key:conditions.append({'x-amz-server-side-encryption-aws-kms-key-id':self.kms_key})
        return self.client.generate_presigned_post(self.bucket,key,Fields=fields,Conditions=conditions,ExpiresIn=expires)

    def verified_upload(self,key,expected_type,max_bytes=25*1024*1024):
        self.validate_key(key)
        metadata=self.client.head_object(Bucket=self.bucket,Key=key)
        if metadata.get('ContentLength',0)>max_bytes or metadata.get('ContentLength',0)<=0:
            raise ValueError('Object outside permitted size')
        if metadata.get('ContentType')!=expected_type:
            raise ValueError('Uploaded content type mismatch')
        if metadata.get('ServerSideEncryption') not in ('AES256','aws:kms'):
            raise ValueError('Unencrypted object rejected')
        return metadata['ContentLength']
