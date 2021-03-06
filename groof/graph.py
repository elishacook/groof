# Copyright (c) 2009 Elisha Cook <elisha@elishacook.com>
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


import struct
import cjson
import threading

try:
    import igraph
    igraph_available = True
except ImportError:
    igraph_available = False


OUTGOING = 0
INCOMING = 1


NODE_KEY_FORMAT = 'Q'
NODE_KEY_SIZE = struct.calcsize(NODE_KEY_FORMAT)
REL_FORMAT = 'I'
REL_SIZE = struct.calcsize(REL_FORMAT)
EDGE_KEY_FORMAT = 'QIQ'
EDGE_KEY_SIZE = struct.calcsize(EDGE_KEY_FORMAT)


def pack_node_key(id):
    return struct.pack(NODE_KEY_FORMAT, id)
    
    
def unpack_node_key(s):
    return struct.unpack(NODE_KEY_FORMAT, s)[0]
    
    
def pack_edge_key(left_id, rel, right_id):
    return struct.pack(EDGE_KEY_FORMAT, left_id, rel, right_id)
    
    
def unpack_edge_key(s):
    return struct.unpack(EDGE_KEY_FORMAT, s)


def invert_edge_key(edge_key_string):
    return edge_key_string[REL_SIZE+NODE_KEY_SIZE:]+\
        edge_key_string[NODE_KEY_SIZE:NODE_KEY_SIZE+REL_SIZE]+\
        edge_key_string[:NODE_KEY_SIZE]
        
        
def pack_edge_key_prefix(node_id, rel):
    if rel is None:
        return pack_node_key(node_id)
    return struct.pack(EDGE_KEY_FORMAT[:2], node_id, rel)



class AttrsMixin(object):
    
    def __getitem__(self, k):
        return self._attrs[k]
        
        
    def __setitem__(self, k, v):
        if k in self._attrs and self._attrs[k] == v:
            return
        self._attrs[k] = v
        self._graph.dirty(self)
        
        
    def __delitem__(self, k):
        if k in self._attrs:
            del self._attrs[k]
            self._graph.dirty(self)
        
        
    def __contains__(self, k):
        return k in self._attrs
        
        
    def items(self):
        return self._attrs.items()
        
        
    def values(self):
        return self._attrs.values()
        
        
    def __iter__(self):
        return self._attrs.__iter__()
    


class Edge(AttrsMixin):
    
    
    def __init__(self, graph, left_id, rel, right_id, attrs=None):
        self._graph = graph
        self.left_id = left_id
        self.rel = rel
        self.right_id = right_id
        self._attrs = attrs if attrs is not None else {}
        
        
    def _get_left(self):
        return self._graph[self.left_id]
    left = property(_get_left)
    
    
    def _get_right(self):
        return self._graph[self.right_id]
    right = property(_get_right)
    
    
    def remove(self):
        self._graph.remove_edge(self)



class Edges():
    
    def __init__(self, graph, node):
        self._graph = graph
        self._node = node
        
        
    def __call__(self, rel=None, other=None, direction=OUTGOING):
        if direction is OUTGOING:
            return self._graph.get_edges(rel, left=self._node, right=other)
        elif direction is INCOMING:
            return self._graph.get_edges(rel, left=other, right=self._node)
        else:
            return self._graph.get_edges(
                rel, left=self._node, right=other)+self._graph.get_edges(
                rel, left=other, right=self._node)
            
            
    def count(self, rel, other=None, direction=OUTGOING):
        if direction is OUTGOING:
            return self._graph.count_edges(rel, left=self._node, right=other)
        elif direction is INCOMING:
            return self._graph.count_edges(rel, left=other, right=self._node)
        else:
            return self._graph.count_edges(
                rel, left=self._node, right=other)+self._graph.count_edges(
                rel, left=other, right=self._node)
        
        
    def add(self, rel, right, **kwargs):
        return self._graph.create_edge(self._node, rel, right, kwargs)



class Node(AttrsMixin):
    
    __slots__ = ('_id', '_attrs', 'edges')
    
    def __init__(self, graph, id, attrs=None):
        object.__setattr__(self, '_graph', graph)
        object.__setattr__(self, '_id', id)
        if attrs is None:
            attrs = {}
        object.__setattr__(self, '_attrs', attrs)
        object.__setattr__(self, 'edges', Edges(self._graph, self))
        
        
    def _get_id(self):
        return self._id
    id = property(_get_id)
    
    
    def delete(self):
        del self._graph[self.id]



class Index(object):
    
    
    def __init__(self, name, graph):
        self._graph = graph
        self._index = self._graph.storage.get_index(name)
        
        
    def __getitem__(self, k):
        try:
            node_id = unpack_node_key(self._index[k])
        except KeyError:
            raise KeyError, "No node found for key %s" % k
        try:
            return self._graph[node_id]
        except KeyError:
            del self._index[k]
            raise KeyError, "No node found for key %s" % k
            
            
    def __setitem__(self, k, node):
        self._index[k] = pack_node_key(node.id)
        
        
    def __delitem__(self, k):
        del self._index[k]
        
        
    def getmulti(self, k):
        try:
            node_ids = self._index.getdup(k)
        except KeyError:
            raise KeyError, "No nodes found for key %s" % k
        nodes = []
        for node_id in node_ids:
            try:
                nodes.append(self._graph[unpack_node_key(node_id)])
            except KeyError:
                pass
        if len(nodes) == 0:
            self._index.deldup(k)
            raise KeyError, "No nodes found for key %s" % k
        return nodes
        
        
    def setmulti(self, k, node):
        self._index.setdup(k, pack_node_key(node.id))
        
        
    def delmulti(self, k):
        self._index.deldup(k)
        
        
    def __iter__(self):
        for k,v in self._index.iter_records():
            yield self._graph[unpack_node_key(v)]



class Graph(object):
    
    def __init__(self, storage):
        self.storage = storage
        try:
            self.last_node_id = self.next_node_id = struct.unpack(
                'Q', self.storage.node[struct.pack('i', 0)])[0]
        except KeyError:
            self.last_node_id = self.next_node_id = 0
            self.storage.node[struct.pack('i', 0)] = struct.pack('Q', 0)
        self._local = threading.local()
        self._reset_change_buffers()
        self._in_context = False
        
        
    def __getitem__(self, node_id):
        k = pack_node_key(node_id)
        try:
            attrs = cjson.decode(self.storage.node[k])
        except KeyError:
            raise KeyError, "No node found with id %s" % node_id
        return Node(self, node_id, attrs)
            
            
    def __delitem__(self, node_id):
        k = pack_node_key(node_id)
        self._local.removed_nodes.add(k)
            
            
    def __len__(self):
        return len(self.storage.node)-1
        
        
    def get_index(self, name):
        return Index(name, self)
        
        
    def stats(self):
        return dict(
            num_nodes = len(self),
            num_edges = len(self.storage.left)
        )
        
        
    def create_node(self, **kwargs):
        self.next_node_id += 1
        n = Node(self, self.next_node_id, kwargs)
        self.dirty(n)
        return n
        
        
    def create_edge(self, left, rel, right, attrs=None):
        k = pack_edge_key(left.id, rel, right.id)
        if k in self.storage.left:
            raise RuntimeError, "This edge already exists"
        e = Edge(self, left.id, rel, right.id, attrs)
        self.dirty(e)
        return e
        
        
    def get_edges(self, rel, left=None, right=None):
        if left is None and right is None:
            raise ValueError, "Must specify at least one of left,right"
        edges = []
        if left is None:
            prefix = pack_edge_key_prefix(right.id, rel)
            for k in self.storage.right.match_prefix(prefix):
                k = invert_edge_key(k)
                (left_id, rel, right_id) = unpack_edge_key(k)
                attrs = self.storage.left[k]
                edges.append(Edge(self, left_id, rel, right_id, attrs))
        elif right is None:
            prefix = pack_edge_key_prefix(left.id, rel)
            for k in self.storage.left.match_prefix(prefix):
                (left_id, rel, right_id) = unpack_edge_key(k)
                attrs = self.storage.left[k]
                edges.append(Edge(self, left_id, rel, right_id, attrs))
        else:
            try:
                attrs = self.storage.left[pack_edge_key(left.id, rel, right.id)]
                edges.append(Edge(self, left.id, rel, right.id, attrs))
            except KeyError:
                pass
        return edges
        
        
    def count_edges(self, rel, left=None, right=None):
        if left is None and right is None:
            raise ValueError, "Must specify at least one of left,right"
        edges = []
        if left is None:
            prefix = pack_edge_key_prefix(right.id, rel)
            return len(self.storage.right.match_prefix(prefix))
        elif right is None:
            prefix = pack_edge_key_prefix(left.id, rel)
            return len(self.storage.left.match_prefix(prefix))
        else:
            return 1 if pack_edge_key(right.id, rel, left.id) in self.storage.right else 0
        
        
    def delete_edge(self, edge):
        self._local.removed_edges.add(pack_edge_key(edge.left_id, edge.rel, edge.right_id))
        
        
    def save(self):
        self.storage.start_txn()
        try:
            for k in self._local.removed_edges:
                try:
                    del self.storage.left[k]
                    del self.storage.left[invert_edge_key(k)]
                except KeyError:
                    pass
            for node_id in self._local.removed_edges:
                node_key = pack_node_key(node_id)
                if node_key in self.storage.node:
                    for k in self.storage.left.match_prefix(node_key):
                        del self.storage.left[k]
                    for k in self.storage.right.match_prefix(node_key):
                        del self.storage.right[k]
                    del self.storage.node[node_key]
            for n in self._local.dirty_nodes:
                self.storage.node[pack_node_key(n.id)] = cjson.encode(n._attrs)
            for e in self._local.dirty_edges:
                k = pack_edge_key(e.left_id, e.rel, e.right_id)
                self.storage.left[k] = cjson.encode(e._attrs)
                self.storage.right[invert_edge_key(k)] = ''
            self._reset_change_buffers()
            num_new_nodes = self.next_node_id - self.last_node_id
            if num_new_nodes > 0:
                self.storage.node[struct.pack('i', 0)] = struct.pack('Q', self.next_node_id)
                self.last_node_id = self.next_node_id
            self.storage.commit_txn()
        except:
            self.storage.abort_txn()
            raise
        
        
    def revert(self):
        self._reset_change_buffers()
        
        
    def __enter__(self):
        self._in_context = True
        self.revert()
        
        
    def __exit__(self, exc, exc_type, tb):
        try:
            if exc:
                self.revert()
            else:
                self.save()
        finally:
            self._in_context = False
        
        
    def dirty(self, item):
        if not self._in_context:
            raise Exception, "Attempting to modify graph outside graph context"
        if isinstance(item, Edge):
            self._local.dirty_edges.add(item)
        else:
            self._local.dirty_nodes.add(item)
            
            
    def to_igraph(self, rel=None, include_edge_attrs=[], directed=True):
        if not igraph_available:
            raise RuntimeError, "igraph library is not available"
        
        num_nodes = len(self)
        
        if len(self) == 0:
            return igraph.Graph()
        
        node_map = {}
        node_ids = []
        nodes = self.storage.node.__iter__()
        nodes.next() # discard 0 record containting next node id
        for i,k in enumerate(nodes):
            node_id = unpack_node_key(k)
            node_map[node_id] = i
            node_ids.append(node_id)
        
        def gen_edges_for_rel():
            for k in self.storage.right:
                k = invert_edge_key(k)
                edge = unpack_edge_key(k)
                if edge[1] == rel:
                    yield k, (node_map[edge[0]],node_map[edge[2]])
        
        def gen_edges():
            for k in self.storage.right:
                k = invert_edge_key(k)
                edge = unpack_edge_key(k)
                yield k, (node_map[edge[0]],node_map[edge[2]])
        
        if rel is None:
            source_edges = gen_edges()
        else:
            source_edges = gen_edges_for_rel()
        
        if include_edge_attrs:
            edge_attrs = dict([(k,[]) for k in include_edge_attrs])
        else:
            edge_attrs = None
        
        if edge_attrs is None:
            edges = [e for k,e in source_edges]
        else:
            edges = []
            for k,e in source_edges:
                edges.append(e)
                attrs = cjson.decode(self.storage.left[k])
                for k in edge_attrs:
                    edge_attrs[k].push(attrs.get(k))
        
        kwargs = dict(edges=edges, directed=directed, vertex_attrs=dict(id=node_ids))
        if edge_attrs is not None:
            kwargs['edge_attrs'] = edge_attrs
        
        return igraph.Graph(**kwargs)
        
        
    def _reset_change_buffers(self):
        self._local.dirty_nodes = set()
        self._local.dirty_edges = set()
        self._local.removed_nodes = set()
        self._local.removed_edges = set()