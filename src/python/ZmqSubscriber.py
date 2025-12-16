###############################################################################
# Copyright 2016 SRI International.  All rights reserved.
#
# The material contained in this file is confidential and proprietary to SRI
# International and may not be reproduced, published, or disclosed to others
# without authorization from SRI International.
#
# DISCLAIMER OF WARRANTIES
#
# SRI International MAKES NO REPRESENTATIONS OR WARRANTIES ABOUT THE
# SUITABILITY OF THE SOFTWARE, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT
# LIMITED TO THE IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE, OR NON-INFRINGEMENT. SRI International SHALL NOT BE
# LIABLE FOR ANY DAMAGES SUFFERED BY LICENSEE AS A RESULT OF USING, MODIFYING
# OR DISTRIBUTING THIS SOFTWARE OR ITS DERIVATIVES
#
###############################################################################

import inspect
import logging
import traceback

import zmq
from zmq.eventloop import ioloop, zmqstream

from ZmqPPWrapper import ZmqPPWrapperType, ZmqPPDecoderFor

class ZmqSubscriber(object):
    """
    ZeroMQ message subscriber.
    """           

    def __init__(self, context, socketAddr, topicFilter, callbackFunc, 
                 zmqDecoderType: ZmqPPWrapperType = ZmqPPWrapperType.BYTES,
                 invertConnection=False, highWaterMark=None, readyEvent = None):
        """Args:

            context (Optional): ZeroMQ Context object. If 'None', a
                new context is created.

            socketAddr: socket address (endpoint) to connect to.  May
                be a single string or a tuple.  If multiple endpoints
                are specified, ZeroMQ will handle the fan-in via "fair
                queuing" (see http://zguide.zeromq.org for more
                details).

            topicFilter: topic filter for subscribing to messages. May
                be a single string, a tuple, a list, or a set.  Each
                filter string is treated as a prefix.  Messages are
                only received on topics that begin with at least one
                of the specified prefixes. An empty filter string is
                used to indicate that this subscriber shall receive
                messages on all topics.

            callbackFunc: function that is invoked when a new message
                arrives.  Receives the topic and the message as its
                two arguments.

            invertConnection (Optional): invert typical ZeroMQ pub/sub
                pattern by make subscribers bind to a socket and
                publishers connect to it.  This is useful when
                publishers are less stable than subscribers.

            highWaterMark[int] (Optional): max number of messages that
                can be queued on this publisher.  Affects both the
                frontend or backend sockets. If not set, internal ZMQ
                default is used.

            readyEvent[threading.Event]: an unset event to be set when
                the subscriber is fully ready to receive and process
                published events. This can be used to coordinate
                threads that can only be started after this subscriber
                is fully ready.
        """
        self.__logger = logging.getLogger(__name__)
        self.__logger.debug("Starting ZmqSubscriber")

        self.readyEvent = None
        if readyEvent:
            assert not readyEvent.isSet(), "readyEvent must be unset"
            self.readyEvent = readyEvent

        if context is None:
            self.__logger.debug("Creating new ZeroMQ context")
            context = zmq.Context()
                        
        self.socket = context.socket(zmq.SUB)  # @UndefinedVariable             
        self.socket.setsockopt(zmq.LINGER, 0)  # @UndefinedVariable

        if highWaterMark:
            self.socket.set_hwm(highWaterMark)
        
        # if socketAddr is a string, convert to tuple
        if isinstance(socketAddr, str):
            socketAddr = (socketAddr,)
            
        for endpoint in socketAddr:
            if invertConnection is False:
                self.__logger.info("Connecting to endpoint=%s" % endpoint)
                self.socket.connect(endpoint)
            else:
                self.__logger.info("Binding to endpoint=%s" % endpoint)
                self.socket.bind(endpoint)
        
        # if topicFilter is a string, convert to tuple
        if isinstance(topicFilter, str):
            self.topicFilter = (topicFilter,)
        else:       
            self.topicFilter = topicFilter
        
        self.callbackFunc = callbackFunc
        # Note: this is needed to remain backwards compatible with callback 
        # functions that do not take topic name as an argument
        callbackIsMethod = inspect.ismethod(self.callbackFunc)
        numCallbackArgs = len(inspect.getfullargspec(self.callbackFunc).args)
        self.callbackFuncNoTopic = numCallbackArgs == 1 or \
            (callbackIsMethod and numCallbackArgs == 2) 

        self.zmqType    = zmqDecoderType
        self.zmqDecoder = ZmqPPDecoderFor (zmqDecoderType)

        self.ioloop = ioloop.ZMQIOLoop()
        stream = zmqstream.ZMQStream(self.socket, self.ioloop)
        stream.on_recv(self.__onRecv)

    def __enter__(self):
        return self
    
    def __exit__(self, *_args):
        self.terminate()

    def run(self):
        """
        Start the subscription event loop.  This method blocks until terminate() is called.
        """
        
        # subscribe to all topics
        for t in self.topicFilter:    
            if isinstance (t, str):
                t = bytes (t, 'utf-8')
            self.socket.setsockopt(zmq.SUBSCRIBE, t)  # @UndefinedVariable
                              
        self.__logger.debug("Starting ZmqSubscriber event loop")
        if self.readyEvent is not None:
            self.readyEvent.set()

        self.ioloop.start()  # block until terminate()
                
        #terminate() has been called
    
        # release the IOLoop resources
        try:
            self.ioloop.close()            
        except: 
            pass # ignore errors
        finally:
            self.ioloop = None

        # close the server socket. This will interrupt blocking receive
        if self.socket and not self.socket.closed:            
            self.socket.close()        
        
    def terminate(self):
        """
        Terminate the subscriber's event loop.  The subscriber cannot be run 
        again after this method has been called.
        """
        self.__logger.info("Cleaning up ZmqSubscriber resources")
        if self.ioloop:            
            self.ioloop.add_callback(lambda x: x.stop(), self.ioloop)      
        
    def __onRecv(self, frames):
        try:
            if len(frames) != 2:
                self.__logger.error("Incorrect number of frames: %d" % len(frames))    
            else:
                # forward the received message to the callback                  
                if self.callbackFuncNoTopic:       
                    self.callbackFunc(frames[1])
                else:
                    # frame[0] is this message's topic; frame[1] are bytes
                    self.callbackFunc(frames[0].decode ('utf-8'), self.zmqDecoder (frames[1]))
        except:
            self.__logger.error("Caught exception in ZmqSubscriber callback:\n%s" % traceback.format_exc(3)) 
