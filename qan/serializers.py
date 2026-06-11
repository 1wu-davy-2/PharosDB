from rest_framework import serializers


class TopQuerySerializer(serializers.Serializer):
    queryid = serializers.CharField()
    fingerprint = serializers.CharField()
    schema = serializers.CharField()
    num_queries = serializers.FloatField()
    total_query_time = serializers.FloatField()
    avg_query_time = serializers.FloatField()
    max_query_time = serializers.FloatField()
    total_rows_sent = serializers.FloatField()
    total_rows_examined = serializers.FloatField()
    total_lock_time = serializers.FloatField()
    no_index_used_count = serializers.FloatField()
    full_scan_count = serializers.FloatField()
    tmp_tables_count = serializers.FloatField()
    example = serializers.CharField(allow_blank=True)


class QueryDetailSerializer(serializers.Serializer):
    queryid = serializers.CharField()
    fingerprint = serializers.CharField()
    schema = serializers.CharField()
    num_queries = serializers.FloatField()
    total_query_time = serializers.FloatField()
    avg_query_time = serializers.FloatField()
    max_query_time = serializers.FloatField()
    min_query_time = serializers.FloatField()
    total_lock_time = serializers.FloatField()
    total_rows_sent = serializers.FloatField()
    total_rows_examined = serializers.FloatField()
    total_rows_affected = serializers.FloatField()
    total_rows_read = serializers.FloatField()
    total_merge_passes = serializers.FloatField()
    total_bytes_sent = serializers.FloatField()
    total_tmp_tables = serializers.FloatField()
    total_tmp_disk_tables = serializers.FloatField()
    full_scan_count = serializers.FloatField()
    full_join_count = serializers.FloatField()
    no_index_used_count = serializers.FloatField()
    no_good_index_used_count = serializers.FloatField()
    total_sort_rows = serializers.FloatField()
    total_sort_scan = serializers.FloatField()
    filesort_count = serializers.FloatField()
    example = serializers.CharField(allow_blank=True)


class TrendPointSerializer(serializers.Serializer):
    hour = serializers.DateTimeField()
    num_queries = serializers.FloatField()
    total_query_time = serializers.FloatField()
    avg_query_time = serializers.FloatField()
    max_query_time = serializers.FloatField()
    total_rows_sent = serializers.FloatField()
    total_rows_examined = serializers.FloatField()


class OverviewSerializer(serializers.Serializer):
    unique_queries = serializers.FloatField()
    total_queries = serializers.FloatField()
    total_query_time = serializers.FloatField()
    avg_query_time = serializers.FloatField()
    total_rows_sent = serializers.FloatField()
    total_rows_examined = serializers.FloatField()
    total_lock_time = serializers.FloatField()
    no_index_queries = serializers.FloatField()
    full_scan_queries = serializers.FloatField()
